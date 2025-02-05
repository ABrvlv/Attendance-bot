import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import csv

# Database setup
conn = sqlite3.connect("balance.db", isolation_level=None)
conn.execute("PRAGMA synchronous = FULL")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
)
""")
conn.commit()

# Create an instance of a bot client
intents = discord.Intents.default()
intents.messages = True  # Enable message intents
intents.guilds = True    # For slash commands
intents.voice_states = True  # To access voice channel information
intents.message_content = True  # Enable access to message content
intents.members = True

client = commands.Bot(command_prefix="!$!", intents=intents)

attendance = app_commands.Group(name="attendance", description="Команды, относящиеся к системе очков за посещения.")
def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result is None:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0) ON CONFLICT(user_id) DO NOTHING", (user_id,))
        conn.commit()
        return 0  # Default starting balance
    return result[0]

# Triggered when the bot is ready
@client.event
async def on_ready():
    print(f'Logged in as {client.user}!')
    try:
        synced = await client.tree.sync()  # Sync the slash commands with Discord
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@client.event
async def on_member_remove(member):
    cursor.execute("DELETE FROM users WHERE user_id = ?", (member.id,))
    conn.commit()

@client.tree.command(name="check_voice", description="Проверяет присутствующих в голосовом канале.")
async def check_voice(interaction: discord.Interaction):
    # Check if the command is used in a thread
    if not interaction.channel or not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message(
            "Эту команду можно использовать только в ветке.",
            ephemeral=True
        )
        return
    
    # Check if the user is in a voice channel
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message(
            "Зайдите в необходимый голосовой канал.",
            ephemeral=True
        )
        return
    
    thread = interaction.channel  # The current thread context
    starter_message = await thread.parent.fetch_message(thread.id)
    if len(starter_message.mentions) == 0:
            await interaction.response.send_message(
            "В сообщении никто не записан.",
            ephemeral=True
            )
            return

    voice_channel = interaction.user.voice.channel

    vc_members = set(voice_channel.members)
    mentions = set(starter_message.mentions)

    not_voice = mentions.difference(vc_members)
    not_message = vc_members.difference(mentions)

    try:
        not_voice = "\n".join([member.mention for member in not_voice])
        not_message = "\n".join([member.mention for member in not_message])

        if not_voice and not_message:
            await interaction.response.send_message(
                f"Записаны, но не в канале:\n{not_voice}\n"
                f"В канале, но без записи:\n{not_message}\n"
            )
        elif not_voice:
            await interaction.response.send_message(
                f"Записаны, но не в канале:\n{not_voice}\n"
            )
        elif not_message:
            await interaction.response.send_message(
                f"В канале, но без записи:\n{not_message}"
            )
        elif not not_voice and not not_message:
            await interaction.response.send_message(
                f"Все в канале! 😎\n"
            )
        else:
            await interaction.response.send_message(
                "Произошла ошибка.",
                ephemeral=True
            )


    except Exception as e:
        await interaction.response.send_message(
            f"Произошла ошибка {e}",
            ephemeral=True
        )
        print(f"{e}")

@client.tree.command(name="give_role", description="Выдает роль всем записанным в ветке.")
async def give_role(interaction: discord.Interaction, role: discord.Role):
    # Ensure the bot has the Manage Roles permission
    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("I don't have permission to manage roles.", ephemeral=True)
        return

    # Ensure the role is below the bot's highest role
    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message("I can't assign roles higher than or equal to my highest role.", ephemeral=True)
        return
    
    # Check if the command is used in a thread
    if not interaction.channel or not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message(
            "Эту команду можно использовать только в ветке.",
            ephemeral=True
        )
        return

    thread = interaction.channel  # The current thread context
    starter_message = await thread.parent.fetch_message(thread.id)
    if len(starter_message.mentions) == 0:
            await interaction.response.send_message(
            "В сообщении никто не записан.",
            ephemeral=True
            )
            return
    
    members = starter_message.mentions
    failed = []
    for member in members:
        try:
            await member.add_roles(role)
        except:
            failed.append(member.display_name)
    if failed:
        await interaction.response.send_message(f"Could not assign {role.name} to: {', '.join(failed)}.")
    else:
        await interaction.response.send_message(f"Роль {role.name} назначена всем записанным пользователям.")


@attendance.command(name="balance", description="Проверить количество очков.")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    if member is None:
        member = interaction.user
    bal = get_balance(member.id)
    await interaction.response.send_message(f"{member.mention}, your balance is {bal} points.")

@attendance.command(name="add", description="Добавить очки пользователю или роли.")
@commands.has_permissions(administrator=True)
async def add(interaction: discord.Interaction, target: discord.Member | discord.Role, amount: int):
    try:
        if isinstance(target, discord.Member):
            cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0) ON CONFLICT(user_id) DO NOTHING", (target.id,))
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target.id))
            conn.commit()
            await interaction.response.send_message(f"Added {amount} points to {target.mention}!")
        elif isinstance(target, discord.Role):
            for member in target.members:
                cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0) ON CONFLICT(user_id) DO NOTHING", (member.id,))
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, member.id))
            conn.commit()
            await interaction.response.send_message(f"Added {amount} points to all members of {target.mention}!")
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}")

@attendance.command(name="remove", description="Удалить очки пользователю или роли.")
@commands.has_permissions(administrator=True)
async def remove(interaction: discord.Interaction, target: discord.Member | discord.Role, amount: int):
    try:
        if isinstance(target, discord.Member):
            cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0) ON CONFLICT(user_id) DO NOTHING", (target.id,))
            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target.id))
            conn.commit()
            await interaction.response.send_message(f"Removed {amount} coins from {target.mention}!")
        elif isinstance(target, discord.Role):
            for member in target.members:
                cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0) ON CONFLICT(user_id) DO NOTHING", (target.id,))
                cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, member.id))
            conn.commit()
            await interaction.response.send_message(f"Removed {amount} coins from all members of {target.mention}!")
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}")

@attendance.command(name="reset", description="Обнулить очки пользователя или роли.")
@commands.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction, target: discord.Member | discord.Role):
    try:
        if isinstance(target, discord.Member):
            cursor.execute("UPDATE users SET balance = 0 WHERE user_id = ?", (target.id,))
            conn.commit()
            await interaction.response.send_message(f"Reset {target.mention}'s balance to 0!")
        elif isinstance(target, discord.Role):
            for member in target.members:
                cursor.execute("UPDATE users SET balance = 0 WHERE user_id = ?", (member.id,))
            conn.commit()
            await interaction.response.send_message(f"Reset balance to 0 for all members of {target.mention}!")
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}")

@attendance.command(name="leaderboard", description="Показать топ 10 пользователей по количеству очков.")
async def leaderboard(interaction: discord.Interaction):
    cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top_users = cursor.fetchall()
    leaderboard_message = "**Leaderboard:**\n"
    for index, (user_id, balance) in enumerate(top_users, start=1):
        member = interaction.guild.get_member(user_id)
        member_name = member.display_name if member else f"User ID: {user_id}"
        leaderboard_message += f"{index}. {member_name} - {balance} points\n"
    await interaction.response.send_message(leaderboard_message)

@attendance.command(name="export", description="Экспортировать всех пользователей и их очки в csv файл.")
async def export(interaction: discord.Interaction, sort_by: str = "balance"):
    if sort_by == "id":
        cursor.execute("SELECT user_id, balance FROM users ORDER BY user_id ASC")
    else:
        cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC")
    users = cursor.fetchall()
    filename = "attendance.csv"
    
    with open(filename, "w", newline="") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["Username", "Balance"])
        for user_id, balance in users:
            member = interaction.guild.get_member(user_id)
            username = member.display_name if member else f"User ID: {user_id}"
            csv_writer.writerow([username, balance])
    
    await interaction.response.send_message(file=discord.File(filename))


client.tree.add_command(attendance)

# Global error handler for all commands
@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandInvokeError):
        await interaction.response.send_message(
            "Something went wrong while executing the command.",
            ephemeral=True
        )
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "You don't have the necessary permissions to use this command.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"An unexpected error occurred. {error}",
            ephemeral=True
        )
    print(f"Command error: {error}")

client.run('')