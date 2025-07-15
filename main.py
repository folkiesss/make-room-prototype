import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

class Client(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.category_name = "MakeRoom"

    async def on_ready(self):
        print(f'Logged in as {self.user.name} - {self.user.id}')

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.content.startswith('hello'):
            await message.channel.send(f'Hello {message.author.name}!')

    async def on_guild_join(self, guild):
        # The embed to be sent
        join_embed = discord.Embed(
            title="🥳 Greeting!",
            description=(
                "Thanks for adding me to your server! I'm here to help you manage things.\n\n"
                "To get started, a moderator can use the `button` below "
                "to create a deficate category for me to work in."
            ),
            color=discord.Color.orange()
        )
        join_embed.set_footer(text="Let's get this server organized!")
        join_embed.set_author(name="MakeRoom")

        create_category_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="✨ Create Category",
            custom_id="create_category"
        )

        create_category_button.callback = self.init_category

        view = discord.ui.View()
        view.add_item(create_category_button)

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
            await guild.create_voice_channel("+ Create Room", category=category)
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


intents = discord.Intents.default()
intents.message_content = True

client = Client(command_prefix='!', intents=intents)
client.run(DISCORD_TOKEN)