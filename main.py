import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

class Client(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.category_name = "MakeRoom"

    async def on_ready(self):
        print(f"Logged in as {self.user.name} (ID: {self.user.id})")

    async def on_message(self, message):
        if message.author == self.user:
            return

        if not message.author.voice or not message.author.voice.channel:
            return
        
        if message.channel.category.name != self.category_name:
            return

        if message.content == str(self.user.name):
            await message.channel.send("は~い!")

        if message.content.startswith("何が好き"):
            await message.channel.send("ウォッカ&ビール よりも　あ・な・た•♡")

    @commands.has_permissions(administrator=True)
    async def on_guild_join(self, guild):
        # The embed to be sent
        print(f"Joined a new guild: {guild.name} (ID: {guild.id})")
        join_embed = discord.Embed(
            title="Greeting! 🤩",
            description=(
                "Thanks for adding me to your server! I'm here to help you manage things.✨\n\n"
                "To get started, a moderator can use the `button` below "
                "to create a deficate category for me to work in."
            ),
            color=discord.Color.orange()
        )
        join_embed.set_footer(text="Let's get this server organized!")
        join_embed.set_author(name=self.user.name, icon_url=self.user.avatar.url)

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

        await guild.system_channel.send(embed=join_embed, view=view)
            
    async def init_category(self, interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=self.category_name)

        # Check if the category already exists
        if category:
            await self.delete_category(interaction)
        
        await self.create_category(interaction)

        embed_color = discord.Color.blue() if category else discord.Color.green()
        embed_title = "Category Recreated" if category else "Category Created"
        embed_description = f"Category '{self.category_name}' created successfully."

        embed = discord.Embed(
            title=embed_title,
            description=embed_description,
            color=embed_color
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def create_category(self, interaction: discord.Interaction):
        guild = interaction.guild
        # Attempt to create the category
        try:
            category = await guild.create_category(self.category_name)
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to create categories.", ephemeral=True)
            return
        
        # Create a voice channel in the new category
        try:
            channel = await guild.create_voice_channel("+ Create Room", category=category)
            await channel.set_permissions(guild.default_role, send_messages=False)
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to create voice channels.", ephemeral=True)
            return

    async def delete_category(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=self.category_name)
        if category:
            try:
                for channel in category.channels:
                    await channel.delete()
                await category.delete()
            except discord.Forbidden:
                await interaction.response.send_message("I do not have permission to delete channels or categories.", ephemeral=True)
                return
        else:
            await interaction.response.send_message("No category named 'MakeRoom' found.", ephemeral=True)

    async def on_voice_state_update(self, member, before, after):
        if after.channel is not None and after.channel.name == "+ Create Room":
            await self.create_new_room(member, after)
        
        # Check if a user left a voice channel and if the channel is empty, delete it
        if before.channel is not None and before.channel.name.endswith("'s Room") and len(before.channel.members) == 0:
            await before.channel.delete()

    async def create_new_room(self, member: discord.Member, after: discord.VoiceState):
        guild = member.guild
        category = after.channel.category
        channel_name = f"🏠 {member.name}'s Room"

        # Check if a channel with the same name already exists
        existing_channel = discord.utils.get(guild.voice_channels, name=channel_name, category=category)
        if existing_channel:
            await member.move_to(existing_channel)
            return

        try:
            new_channel = await guild.create_voice_channel(name=channel_name, category=category)
            await member.move_to(new_channel)
            await self.room_control(new_channel, member)
        except discord.Forbidden:
            # Handle the case where the bot doesn't have permissions
            print(f"I do not have permission to create voice channels in {guild.name}")
        except Exception as e:
            print(f"An error occurred: {e}")

    async def room_control(self, channel: discord.VoiceChannel, creator: discord.Member):
        # Embed to be sent in the voice channel
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

        await channel.send(
            embed=control_embed,
            view=view
        )

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
            # Toggle the visibility of the voice channel
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
    

intents = discord.Intents.default()
intents.message_content = True

client = Client(command_prefix='!', intents=intents)
client.run(DISCORD_TOKEN)