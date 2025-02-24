import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View
import csv
from pagination import Pagination
from config import TOKEN, COIN, BACKUP_GUILD_CHANNEL
import datetime, time
from giveaway import GiveawayButton, check_active_giveaways, giveaway_end
from database import get_guild_db
from logger import logger

# Create an instance of a bot client
intents = discord.Intents.default()
intents.messages = True  # Enable message intents
intents.guilds = True    # For slash commands
intents.voice_states = True  # To access voice channel information
intents.message_content = True  # Enable access to message content
intents.members = True

client = commands.Bot(command_prefix="!$!", intents=intents)
points = app_commands.Group(name="points", description="Команды, относящиеся к системе очков за посещения.")
points_ = app_commands.Group(name="points_a", description="Административные команды, относящиеся к системе очков за посещения.")

active_giveaways = []

# Triggered when the bot is ready
@client.event
async def on_ready():
    print(f'Logged in as {client.user}!')
    try:
        synced = await client.tree.sync()  # Sync the slash commands with Discord
        logger.debug("start")
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    if not daily_task.is_running():
        daily_task.start()
    global active_giveaways 
    active_giveaways = await check_active_giveaways(client)
    if not giveaways_task.is_running():
        giveaways_task.start()

@client.event
async def on_member_remove(member):
    conn, cursor = get_guild_db(member.guild.id)
    cursor.execute("DELETE FROM users WHERE user_id = ?", (member.id,))
    conn.commit()
    logger.info(f"{member.display_name} deleted as they left the server.")

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
        await interaction.response.defer()
        not_voice = "\n".join([member.mention for member in not_voice])
        not_message = "\n".join([member.mention for member in not_message])

        if not_voice and not_message:
            await interaction.followup.send(
                f"Записаны, но не в канале:\n{not_voice}\n"
                f"В канале, но без записи:\n{not_message}\n"
            )
        elif not_voice:
            await interaction.followup.send(
                f"Записаны, но не в канале:\n{not_voice}\n"
            )
        elif not_message:
            await interaction.followup.send(
                f"В канале, но без записи:\n{not_message}"
            )
        elif not not_voice and not not_message:
            await interaction.followup.send(
                f"Все в канале! 😎\n"
            )
        else:
            await interaction.followup.send(
                "Произошла ошибка.",
                ephemeral=True
            )

    except Exception as e:
        await interaction.followup.send(
            f"Произошла ошибка {e}",
            ephemeral=True
        )
        logger.error(f"check_voice: {e}")

@client.tree.command(name="give_role", description="Выдает роль всем записанным в ветке.")
@app_commands.default_permissions(manage_roles=True)
async def give_role(interaction: discord.Interaction, role: discord.Role):
    try:
        await interaction.response.defer()
        # Ensure the bot has the Manage Roles permission
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.followup.send("I don't have permission to manage roles.", ephemeral=True)
            return

        # Ensure the role is below the bot's highest role
        if role >= interaction.guild.me.top_role:
            await interaction.followup.send("I can't assign roles higher than or equal to my highest role.", ephemeral=True)
            return
        
        # Check if the command is used in a thread
        if not interaction.channel or not isinstance(interaction.channel, discord.Thread):
            await interaction.followup.send(
                "Эту команду можно использовать только в ветке.",
                ephemeral=True
            )
            return

        thread = interaction.channel  # The current thread context
        starter_message = await thread.parent.fetch_message(thread.id)
        if len(starter_message.mentions) == 0:
                await interaction.followup.send(
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
            await interaction.followup.send(f"Could not assign {role.name} to: {', '.join(failed)}.")
        else:
            await interaction.followup.send(f"Роль {role.name} назначена всем записанным пользователям.")
            logger.debug(f"give_role: {role.name}")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"give_role: {e}")

@points.command(name="balance", description="Проверить количество очков.")
@app_commands.describe(member='Участник (необязательно)')
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    try:
        await interaction.response.defer()
        conn, cursor = get_guild_db(interaction.guild.id)
        if member is None:
            member = interaction.user
        cursor.execute("INSERT INTO users (user_id, balance, total_balance, join_date) VALUES (?, 0, 0, ?) ON CONFLICT(user_id) DO NOTHING", (member.id, time.strftime('%Y-%m-%d', time.localtime())))
        cursor.execute("SELECT balance, total_balance FROM users WHERE user_id = ?", (member.id,))
        result = cursor.fetchone()

        embed = discord.Embed(title= f"Баланс {member.display_name}")
        embed.add_field(name="Орешки", value=f"{result[0]} {COIN}")
        embed.add_field(name="Активность", value=f"{result[1]}")
        try:
            await interaction.followup.send(embed=embed)
        except discord.NotFound:
            logger.error("Interaction expired before response could be sent.")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"balance: {e}")

@points_.command(name="add", description="Добавить очки пользователю или роли.")
@app_commands.describe(target='Участник или роль', amount='Количество')
@app_commands.checks.has_permissions(manage_roles=True)
async def add(interaction: discord.Interaction, target: discord.Member | discord.Role, amount: int):
    try:
        await interaction.response.defer()
        conn, cursor = get_guild_db(interaction.guild.id)
        if isinstance(target, discord.Member):
            cursor.execute("INSERT INTO users (user_id, balance, total_balance, join_date) VALUES (?, 0, 0, ?) ON CONFLICT(user_id) DO NOTHING", (target.id, time.strftime('%Y-%m-%d', time.localtime())))
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target.id))
            cursor.execute("UPDATE users SET total_balance = total_balance + ? WHERE user_id = ?", (amount, target.id))
            logger.info(f"{target.display_name} added {amount}.")
            conn.commit()
            await interaction.followup.send(f"Добавлено {amount} {COIN} для {target.mention}!")
        elif isinstance(target, discord.Role):
            for member in target.members:
                cursor.execute("INSERT INTO users (user_id, balance, total_balance, join_date) VALUES (?, 0, 0, ?) ON CONFLICT(user_id) DO NOTHING", (member.id, time.strftime('%Y-%m-%d', time.localtime())))
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, member.id))
                cursor.execute("UPDATE users SET total_balance = total_balance + ? WHERE user_id = ?", (amount, member.id))
                logger.info(f"{member.display_name} added {amount}.")
            conn.commit()
            await interaction.followup.send(f"Добавлено {amount} {COIN} для {target.mention}!")
            
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"add: {e}")

@points_.command(name="thread_add", description="Добавить очки записанным в ветке.")
@app_commands.describe(amount='Количество')
@app_commands.checks.has_permissions(manage_roles=True)
async def thread_add(interaction: discord.Interaction, amount: int):
    # Check if the command is used in a thread
    if not interaction.channel or not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message(
            "Эту команду можно использовать только в ветке.",
            ephemeral=True
        )
        return

    try:
        await interaction.response.defer()
        conn, cursor = get_guild_db(interaction.guild.id)
        thread = interaction.channel  # The current thread context
        starter_message = await thread.parent.fetch_message(thread.id)
 
        if len(starter_message.mentions) == 0:
            await interaction.followup.send(
            "В сообщении никто не записан.",
            ephemeral=True
            )
            return
    
        members = starter_message.mentions

        skipped_users = []
        for member in members:
            guild_member = interaction.guild.get_member(member.id)
            if guild_member is None:
                try:
                    guild_member = await interaction.guild.fetch_member(member.id)
                except discord.NotFound:
                    skipped_users.append(member.display_name)
                    continue

            cursor.execute("INSERT INTO users (user_id, balance, total_balance, join_date) VALUES (?, 0, 0, ?) ON CONFLICT(user_id) DO NOTHING", (member.id, time.strftime('%Y-%m-%d', time.localtime())))
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, member.id))
            cursor.execute("UPDATE users SET total_balance = total_balance + ? WHERE user_id = ?", (amount, member.id))
            logger.info(f"{member.display_name} added {amount}.")
        conn.commit()

        if skipped_users:
            await interaction.followup.send(f"Пользователи покинули сервер и были пропущены: {', '.join(skipped_users)}.", ephemeral=True)
        await interaction.followup.send(f"Добавлено {amount} {COIN} всем записанным пользователям!")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"thread_add: {e}")

@points_.command(name="reaction_add", description="Добавить очки тем, кто поставил реакцию ✅.")
@app_commands.describe(amount='Количество')
@app_commands.checks.has_permissions(manage_roles=True)
async def reaction_add(interaction: discord.Interaction, amount: int):
    # Check if the command is used in a thread
    if not interaction.channel or not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message(
            "Эту команду можно использовать только в ветке.",
            ephemeral=True
        )
        return

    try:
        await interaction.response.defer()
        conn, cursor = get_guild_db(interaction.guild.id)
        thread = interaction.channel  # The current thread context
        starter_message = await thread.parent.fetch_message(thread.id)
        members = []
        if len(starter_message.reactions) == 0:
            await interaction.followup.send(
            "В сообщении нет реакций.",
            ephemeral=True
            )
            return

        for reaction in starter_message.reactions:
            if str(reaction.emoji) == "✅":
                members = [user async for user in reaction.users()]
        if not members:
            await interaction.followup.send("В сообщении нет реакций.")
            return
        skipped_users = []
        for member in members:
            guild_member = interaction.guild.get_member(member.id)
            if guild_member is None:
                try:
                    guild_member = await interaction.guild.fetch_member(member.id)
                except discord.NotFound:
                    skipped_users.append(member.display_name)
                    continue
                
            cursor.execute("INSERT INTO users (user_id, balance, total_balance, join_date) VALUES (?, 0, 0, ?) ON CONFLICT(user_id) DO NOTHING", (member.id, time.strftime('%Y-%m-%d', time.localtime())))
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, member.id))
            cursor.execute("UPDATE users SET total_balance = total_balance + ? WHERE user_id = ?", (amount, member.id))
            logger.info(f"{member.display_name} added {amount}.")
        conn.commit()

        if skipped_users:
            await interaction.followup.send(f"Пользователи покинули сервер и были пропущены: {', '.join(skipped_users)}.", ephemeral=True)
        
        await interaction.followup.send(f"Добавлено {amount} {COIN} всем, кто поставил ✅!")
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"reaction_add: {e}")


@points_.command(name="remove", description="Удалить очки пользователю или роли.")
@app_commands.describe(target='Пользователь или роль', amount='Количество', points='Какие очки удалить? (Текущие по умолчанию)')
@app_commands.choices(points=[
    discord.app_commands.Choice(name='Текущие', value=0),
    discord.app_commands.Choice(name='Постоянные', value=1),
    discord.app_commands.Choice(name='Оба', value=2),
])
@app_commands.checks.has_permissions(manage_roles=True)
async def remove(interaction: discord.Interaction, target: discord.Member | discord.Role, amount: int, points: int = 0):
    try:
        await interaction.response.defer()
        conn, cursor = get_guild_db(interaction.guild.id)
        if isinstance(target, discord.Member):
            cursor.execute("INSERT INTO users (user_id, balance, total_balance, join_date) VALUES (?, 0, 0, ?) ON CONFLICT(user_id) DO NOTHING", (target.id, time.strftime('%Y-%m-%d', time.localtime())))
            if points == 1: 
                cursor.execute("UPDATE users SET total_balance = total_balance - ? WHERE user_id = ?", (amount, target.id))
            elif points == 2:
                cursor.execute("UPDATE users SET balance = balance - ?, total_balance = total_balance - ? WHERE user_id = ?", (amount, amount, target.id))
            else:
                cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target.id))
            conn.commit()
            logger.info(f"{target.display_name} removed {amount} from {points}.")
            await interaction.followup.send(f"Удалено {amount} {COIN} у {target.mention}!")
        elif isinstance(target, discord.Role):
            for member in target.members:
                cursor.execute("INSERT INTO users (user_id, balance, total_balance, join_date) VALUES (?, 0, 0, ?) ON CONFLICT(user_id) DO NOTHING", (member.id, time.strftime('%Y-%m-%d', time.localtime())))
                if points == 1: 
                    cursor.execute("UPDATE users SET total_balance = total_balance - ? WHERE user_id = ?", (amount, member.id))
                elif points == 2:
                    cursor.execute("UPDATE users SET balance = balance - ?, total_balance = total_balance - ? WHERE user_id = ?", (amount, amount, member.id))
                else:
                    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, member.id))
                logger.info(f"{member.display_name} removed {amount} from {points}.")
            conn.commit()
            await interaction.followup.send(f"Удалено {amount} {COIN} у {target.mention}!")

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"remove: {e}")

@points_.command(name="reset", description="Обнулить очки пользователя или роли.")
@app_commands.describe(target='Пользователь или роль', points='Какие очки обнулить? (Текущие по умолчанию)')
@app_commands.choices(points=[
    discord.app_commands.Choice(name='Текущие', value=0),
    discord.app_commands.Choice(name='Постоянные', value=1),
    discord.app_commands.Choice(name='Оба', value=2),
])
@app_commands.checks.has_permissions(manage_roles=True)
async def reset(interaction: discord.Interaction, target: discord.Member | discord.Role, points: int = 0):
    try:
        await interaction.response.defer()
        conn, cursor = get_guild_db(interaction.guild.id)
        if isinstance(target, discord.Member):    
            cursor.execute("INSERT INTO users (user_id, balance, total_balance, join_date) VALUES (?, 0, 0, ?) ON CONFLICT(user_id) DO NOTHING", (target.id, time.strftime('%Y-%m-%d', time.localtime())))
            if points == 1: 
                cursor.execute("UPDATE users SET total_balance = 0 WHERE user_id = ?", (target.id,))
            elif points == 2:
                    cursor.execute("UPDATE users SET balance = 0, total_balance = 0 WHERE user_id = ?", (target.id,))
            else:
                cursor.execute("UPDATE users SET balance = 0 WHERE user_id = ?", (target.id,))
            conn.commit()
            logger.info(f"{target.display_name} reseted to 0.")
            await interaction.followup.send(f"Баланс {target.mention} обнулен {COIN}!")
        elif isinstance(target, discord.Role):
            for member in target.members:
                cursor.execute("INSERT INTO users (user_id, balance, total_balance, join_date) VALUES (?, 0, 0, ?) ON CONFLICT(user_id) DO NOTHING", (member.id, time.strftime('%Y-%m-%d', time.localtime())))
                if points == 1: 
                    cursor.execute("UPDATE users SET total_balance = 0 WHERE user_id = ?", (member.id,))
                elif points == 2:
                    cursor.execute("UPDATE users SET balance = 0, total_balance = 0 WHERE user_id = ?", (member.id,))
                else:
                    cursor.execute("UPDATE users SET balance = 0 WHERE user_id = ?", (member.id,))
                logger.info(f"{member.display_name} reseted to 0.")
            conn.commit()
            await interaction.followup.send(f"Баланс {target.mention} обнулен {COIN}!")

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"reset: {e}")

@points.command(name="leaderboard", description="Показать топ 10 пользователей по количеству очков.")
@app_commands.describe(
    points='Какие очки вывести? (Очки по умолчанию)'
    )
@app_commands.choices(points=[
    discord.app_commands.Choice(name='Очки', value=0),
    discord.app_commands.Choice(name='Активность', value=1),
])
async def leaderboard(interaction: discord.Interaction, points: int = 0):
    try:
        await interaction.response.defer()
        conn, cursor = get_guild_db(interaction.guild.id)
        if points: 
            cursor.execute("SELECT user_id, total_balance FROM users ORDER BY total_balance DESC")
            title = f"Таблица лидеров по активности"
        else: 
            cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC")
            title = f"{COIN} Таблица лидеров по очкам {COIN}"
        users = cursor.fetchall()
        async def get_page(page: int):
            embed = discord.Embed(title=title, description="")
            offset = (page-1) * 10
            for rank, (user_id, balance) in enumerate(users[offset:offset+10]):
                user = interaction.guild.get_member(user_id)
                username = user.display_name if user else f"{user_id}"
                embed.description += f"{(rank+1)+(page-1)*10}. {username} – {balance} {COIN}\n"
            n = Pagination.compute_total_pages(len(users), 10)
            embed.set_footer(text=f"Страница {page} из {n}")
            return embed, n
        await Pagination(interaction, get_page).navigate()
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"leaderboard: {e}")

@points_.command(name="export", description="Экспортировать всех пользователей и их очки в csv файл.")
@app_commands.describe(sort='Сортировать по: (Постоянный баланс по умолчанию)')
@app_commands.choices(sort=[
    discord.app_commands.Choice(name='Имена', value=0),
    discord.app_commands.Choice(name='Постоянные', value=1),
    discord.app_commands.Choice(name='Текущие', value=2),
])
@app_commands.checks.has_permissions(manage_roles=True)
async def export(interaction: discord.Interaction, sort: int = 1):
    try:
        await interaction.response.defer()
        conn, cursor = get_guild_db(interaction.guild.id)
        cursor.execute("SELECT user_id, total_balance, balance, CAST(julianday('now') - julianday(join_date) AS INT) AS days_since_join FROM users")
        users = cursor.fetchall()
        
        if sort == 0:
            users.sort(key=lambda x: x[0])
        elif sort == 2:
            users.sort(key=lambda x: x[2], reverse=True)
        else:
            users.sort(key=lambda x: x[1], reverse=True)
        
        with open("attendance.csv", "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Username", "Total Balance", "Balance", "Total / Day"])
            for user_id, total_balance, balance, days_since_join in users:
                user = interaction.guild.get_member(user_id)
                username = user.display_name if user else f"{user_id}"
                if days_since_join: activity = round(total_balance/days_since_join, 2)
                else: activity = total_balance
                writer.writerow([username, total_balance, balance, activity])
        
        await interaction.followup.send(file=discord.File("attendance.csv"))
        logger.info(f"export called.")

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"export: {e}")

@points_.command(name="log", description="Экспортировать лог-файл в канал.")
@app_commands.checks.has_permissions(manage_roles=True)
async def log(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
        
        await interaction.followup.send(file=discord.File("bot.log"))
        logger.info(f"log called.")

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"export: {e}")


@points_.command(name="giveaway", description="Начать розыгрыш.")
@app_commands.describe(prize="Предмет для розыгрыша.", points="Сколько очков стоит участие?", duration="Длительность розыгрыша в часах.")
@app_commands.checks.has_permissions(manage_roles=True)
async def giveaway(interaction: discord.Interaction, prize: str, points: int, duration: int):
    try:
        global active_giveaways
        end_time = int(time.time()) + duration*3600
        embed = discord.Embed(title="🎉 РОЗЫГРЫШ 🎉", description=f"**## {prize}**\n**Нажмите кнопку ниже, чтобы участвовать!\nСтоимость участия: {points} {COIN}**\nМожно купить несколько билетов!\n\nЗавершается: <t:{end_time}:R> (<t:{end_time}:f>)", color=discord.Color.gold())
        embed.add_field(name = "", value=f"Участников: 0")

        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()

        view = View(timeout=None)
        view.add_item(GiveawayButton(message.id, points, prize))
        client.add_view(view)
        await interaction.edit_original_response(view=view)

        conn, cursor = get_guild_db(interaction.guild.id)
        cursor.execute("INSERT INTO giveaways (message_id, channel_id, guild_id, prize, points, end_time) VALUES (?, ?, ?, ?, ?, ?)", (message.id, interaction.channel.id, interaction.guild.id, prize, points, end_time))
        conn.commit()
        logger.info(f"New giveaway {prize}.")
        active_giveaways.append((message.id, interaction.channel.id, interaction.guild.id, prize, points, end_time))
        active_giveaways.sort(key=lambda x: x[5])
        
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
        logger.error(f"giveaway: {e}")

@tasks.loop(seconds=10)
async def giveaways_task():
    global active_giveaways
    if active_giveaways:
        end_time = active_giveaways[0][5]
        if end_time <= int(time.time()):
            await giveaway_end(client, active_giveaways[0])
            active_giveaways.pop(0)


@tasks.loop(time=datetime.time(hour=0, minute=0))  # Backup loop
async def daily_task():
    await client.wait_until_ready()
    channel = client.get_channel(BACKUP_GUILD_CHANNEL)
    guild = channel.guild
    conn, cursor = get_guild_db(guild.id)
    cursor.execute("SELECT user_id, total_balance, balance FROM users")
    users = cursor.fetchall()
    users.sort(key=lambda x: x[1], reverse=True)
    with open("balances.csv", "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Username", "Total Balance", "Balance"])
        for user_id, total_balance, balance in users:
            user = guild.get_member(user_id)
            username = user.display_name if user else f"Unknown ({user_id})"
            writer.writerow([username, total_balance, balance])
    
    if channel:
        await channel.send(file=discord.File("balances.csv"))
        logger.info(f"Daily backup.")
    else:
        logger.error(f"daily_task: Channel with ID {BACKUP_GUILD_CHANNEL} not found.")


client.tree.add_command(points)
client.tree.add_command(points_)

# Global error handler for all commands
@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandInvokeError):
        await interaction.response.send_message(
            "Something went wrong while executing the command.",
            ephemeral=True
        )
        logger.error(f"{interaction.command}: {error}")
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "You don't have the necessary permissions to use this command.",
            ephemeral=True
        )
        logger.error(f"{interaction.command}: {error}")
    else:
        await interaction.response.send_message(
            f"An unexpected error occurred. {error}",
            ephemeral=True
        )
        logger.error(f"{interaction.command}: {error}")
    print(f"Command error: {error}")

client.run(TOKEN)