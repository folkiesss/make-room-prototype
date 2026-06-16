import discord
from discord import app_commands
import os
import logging
from dotenv import load_dotenv

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('MakeRoomBot')

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

class Client(discord.Client):
    def __init__(self, intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.category_name = "MakeRoom"
        self.honeypot_channel_name = "dusty-locker"

    async def setup_hook(self):
        # Attach the global error handler
        self.tree.on_error = self.on_app_command_error
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s) globally.")
        except Exception as e:
            logger.error(f"Error syncing commands: {e}")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("⛔ You don't have the required permissions to use this command.", ephemeral=True)
        else:
            error_msg = "Oops! Something went wrong while running that command."
            if interaction.response.is_done():
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.response.send_message(error_msg, ephemeral=True)
            logger.error(f"Command Error: {error}")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user.name} (ID: {self.user.id})")

    # --------------------------------------------------
    # EVENTS
    # --------------------------------------------------

    async def on_message(self, message):
        if message.author == self.user:
            return

        # Honeypot Trigger
        if message.channel.name == self.honeypot_channel_name:
            await self.honey_pot_trigger(message)
            return

        # Text Triggers
        if message.content == str(self.user.name):
            await message.channel.send("は~い!", ephemeral=True)

        if message.content.startswith("何が好き"):
            await message.channel.send("ウォッカ&ビール よりも あ・な・た・♡", ephemeral=True)

    async def on_guild_join(self, guild):
        logger.info(f"Joined a new guild: {guild.name} (ID: {guild.id})")
        join_embed = discord.Embed(
            title="Greeting! 🤩",
            description=(
                "Thanks for adding me to your server! I'm here to help you manage things.✨\n\n"
                "To get started, a moderator can use the `button` below "
                "to create a dedicated category for me to work in."
            ),
            color=discord.Color.orange()
        )
        join_embed.set_footer(text="Let's get this server organized!")
        if self.user.avatar:
            join_embed.set_author(name=self.user.name, icon_url=self.user.avatar.url)
        else:
            join_embed.set_author(name=self.user.name)

        create_category_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="✨ Create Category",
            custom_id="create_category"
        )
        create_category_button.callback = self.init_category

        view = discord.ui.View()
        view.add_item(create_category_button)

        for channel in guild.text_channels:
            if channel.name == "moderator-only":
                await channel.send(embed=join_embed, view=view)
                return

        if guild.system_channel:
            await guild.system_channel.send(embed=join_embed, view=view)

    async def on_voice_state_update(self, member, before, after):
        # User joins the creator channel
        if after.channel is not None and after.channel.name == "+ Create Room":
            await self.create_new_room(member, after)
        
        # Room cleanup logic
        if before.channel is not None:
            category = before.channel.category
            if category and category.name == self.category_name and before.channel.name != "+ Create Room":
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete()
                        logger.info(f"Deleted empty room: {before.channel.name}")
                    except discord.DiscordException:
                        pass

    # --------------------------------------------------
    # CATEGORY & ROOM LOGIC
    # --------------------------------------------------

    async def init_category(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=self.category_name)

        if category:
            success = await self.delete_category(interaction)
            if not success:
                return

        channel = await self.create_category(interaction)
        if not channel:
            return

        embed_color = discord.Color.blue() if category else discord.Color.green()
        embed_title = "Category Recreated" if category else "Category Created"
        embed_description = (
            f"Category '{self.category_name}' created successfully.\n"
            f"You can now join <#{channel.id}> to create your own voice rooms!"
        )

        embed = discord.Embed(
            title=embed_title,
            description=embed_description,
            color=embed_color
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"Category initialized by {interaction.user} in {guild.name}")

    async def create_category(self, interaction: discord.Interaction):
        guild = interaction.guild
        try:
            category = await guild.create_category(self.category_name)
        except discord.Forbidden:
            await interaction.followup.send("I do not have permission to create categories.", ephemeral=True)
            return None
        
        try:
            channel = await guild.create_voice_channel("+ Create Room", category=category)
            await channel.set_permissions(guild.default_role, view_channel=True, connect=True)
            return channel
        except discord.Forbidden:
            await interaction.followup.send("I do not have permission to create voice channels.", ephemeral=True)
            return None
        
    async def delete_category(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=self.category_name)
        if category:
            try:
                for channel in category.channels:
                    await channel.delete()
                await category.delete()
                return True
            except discord.Forbidden:
                await interaction.followup.send("I do not have permission to delete channels or categories.", ephemeral=True)
                return False
        return True

    async def create_new_room(self, member: discord.Member, after: discord.VoiceState):
        guild = member.guild
        category = after.channel.category
        channel_name = f"🏠 {member.nick if member.nick else member.name}'s Room"

        existing_channel = discord.utils.get(guild.voice_channels, name=channel_name, category=category)
        if existing_channel:
            await member.move_to(existing_channel)
            return

        try:
            new_channel = await guild.create_voice_channel(name=channel_name, category=category)
            await member.move_to(new_channel)
            await self.room_control(new_channel, member)
            logger.info(f"Created new room: {channel_name} in {guild.name}")
        except discord.Forbidden:
            logger.warning(f"I do not have permission to create voice channels in {guild.name}")
        except Exception as e:
            logger.error(f"Error creating room: {e}")

    async def room_control(self, channel: discord.VoiceChannel, creator: discord.Member):
        control_embed = discord.Embed(
            title="🪄 Room Control",
            description="Toggle the visibility of this voice channel.",
            color=discord.Color.og_blurple()
        )
        control_embed.set_footer(text="Manage your room privacy!")

        toggle_visibility_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Toggle Visibility",
            custom_id="toggle_visibility"
        )
        toggle_visibility_button.callback = lambda interaction: self.toggle_visibility(interaction, creator)

        view = discord.ui.View()
        view.add_item(toggle_visibility_button)
        await channel.send(embed=control_embed, view=view)

    async def toggle_visibility(self, interaction: discord.Interaction, creator: discord.Member):
        channel = interaction.channel
        if interaction.user != creator:
            warn_embed = discord.Embed(
                title="⚠️ Permission Denied",
                description="You can only manage the room you created.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=warn_embed, ephemeral=True)
            return
        
        if isinstance(channel, discord.VoiceChannel):
            if channel.permissions_for(interaction.guild.default_role).view_channel:
                await channel.set_permissions(interaction.guild.default_role, view_channel=False)
                await channel.set_permissions(interaction.user, view_channel=True)
                embed = discord.Embed(
                    title="😶‍🌫️ Room Privacy",
                    description="This room is now private.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await channel.set_permissions(interaction.guild.default_role, view_channel=True)
                embed = discord.Embed(
                    title="🥳 Room Privacy",
                    description="This room is now public.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("This command can only be used in a voice channel.", ephemeral=True)

    # --------------------------------------------------
    # COMMAND AND HONEYPOT LOGIC
    # --------------------------------------------------

    async def init_honeypot(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        channel_name = self.honeypot_channel_name

        try:
            # 1. Check for and delete the existing channel safely
            existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
            if existing_channel:
                await existing_channel.delete(reason="Re-initializing honeypot channel")
            
            # 2. Create the new honeypot channel
            honeypot_channel = await guild.create_text_channel(channel_name)
            
            # 3. Set permissions (Allows the default role to send messages)
            await honeypot_channel.set_permissions(guild.default_role, send_messages=True)

            # 4. Construct and send the embed
            embed = discord.Embed(
                title="What is this place? This locker is so dusty... 😶‍🌫️",
                description=(
                    f"There's a pile of dangerous dust inside, and it's best to leave it alone!\n " # Added space here
                    f"Better not to touch this locker or {self.user.name} will be very upset! 😠\n\n"
                    f"Sending a message here will trigger an automatic ban. 🚫" # Removed the trailing 'f"."' to keep it clean
                ),
            )
            embed.set_footer(text=f"with love ^ ^, {self.user.name}✨")
            
            await honeypot_channel.send(embed=embed)
            
            # 5. Confirm with the user who ran the command
            await interaction.followup.send(f"✅ Honeypot ready! Warning placed in {honeypot_channel.mention}.", ephemeral=True)
            logger.info(f"Successfully initialized honeypot in '{guild.name}'.")
            
        except discord.Forbidden:
            logger.warning(f"Missing permissions in '{guild.name}'.")
            await interaction.followup.send(
                "❌ I don't have the necessary permissions! Please ensure I have `Manage Channels` and `Send Messages`.", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error(f"HTTP Exception during honeypot init in '{guild.name}': {e}")
            await interaction.followup.send("❌ Discord had a hiccup while making the channel. Try again!", ephemeral=True)

    async def debug(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ You are not connected to a voice channel!", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        await interaction.response.send_message(f"🎙️ **Voice channel:** {channel.name} \n🆔 **ID:** `{channel.id}`", ephemeral=True)
        logger.info(f"{interaction.user} requested debug info for channel: {channel.name}")

    async def honey_pot_trigger(self, message):
        if message.author.bot:
            return

        mod_channel = discord.utils.get(message.guild.text_channels, name="moderator-only")
        is_admin = getattr(message.author, 'guild_permissions', None) and message.author.guild_permissions.administrator

        if is_admin:
            if mod_channel:
                embed = discord.Embed(
                    title="⚠️ Honeypot Triggered - Admin",
                    description="A user with administrator permissions triggered the honeypot, but was not banned.",
                    color=discord.Color.orange()
                )
                embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
                embed.set_footer(text="No action taken - user is a moderator.")
                if message.author.avatar:
                    embed.set_author(name=message.author.name, icon_url=message.author.avatar.url)
                else:
                    embed.set_author(name=message.author.name)
                await mod_channel.send(embed=embed)
                
            await message.channel.send("Moderators are not affected by the honeypot.", delete_after=5)
            try:
                await message.delete(delay=5)
            except discord.HTTPException:
                pass
            return

        try:
            await message.author.ban(reason="Honeypot triggered", delete_message_seconds=600)
            logger.info(f"User {message.author} was banned via honeypot in {message.guild.name}")
            
            if mod_channel:
                embed = discord.Embed(
                    title="🚨 Honeypot Activated",
                    description="A user has been automatically banned.",
                    color=discord.Color.brand_red()
                )
                embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
                embed.add_field(name="Reason", value="Posted a message in the `#dusty-locker` honeypot channel.", inline=False)
                if message.author.avatar:
                    embed.set_author(name=message.author.name, icon_url=message.author.avatar.url)
                else:
                    embed.set_author(name=message.author.name)
                await mod_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to ban user {message.author} from honeypot: {e}")


# ==================================================
# BOT INITIALIZATION & COMMAND REGISTRATION
# ==================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

client = Client(intents=intents)

@client.tree.command(name="init_honeypot", description="Initialize the honeypot channel with a warning message.")
@app_commands.checks.has_permissions(administrator=True) 
async def init_honeypot(interaction: discord.Interaction):
    await client.init_honeypot(interaction)

@client.tree.command(name="debug", description="Get info about your current voice channel.")
@app_commands.checks.has_permissions(administrator=True) 
async def debug(interaction: discord.Interaction):
    await client.debug(interaction)

# Pass logging control to our custom setup
discord.utils.setup_logging() 
client.run(DISCORD_TOKEN, log_handler=None)