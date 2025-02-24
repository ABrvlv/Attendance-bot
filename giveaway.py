import discord
from database import get_guild_db
from discord.ui import Button, View
from config import GUILD_ID
from discord.ui import View
import asyncio, random
from logger import logger

class GiveawayButton(Button):
    def __init__(self, giveaway_id, points, prize):
        super().__init__(label="Участвовать", style=discord.ButtonStyle.green, custom_id=f"giveaway_{giveaway_id}")
        self.giveaway_id = giveaway_id
        self.points = points
        self.prize = prize
        self.last_edit = 0
        self.edit_lock = asyncio.Lock()
        self.update_task = None

    async def callback(self, button_interaction: discord.Interaction):
        await button_interaction.response.defer(ephemeral=True)
        if not button_interaction.message.components:
            return
        conn, cursor = get_guild_db(button_interaction.guild.id)
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (button_interaction.user.id,))
        user_balance = cursor.fetchone()
        
        if not user_balance or user_balance[0] < self.points:
            await button_interaction.followup.send("Недостаточно очков!", ephemeral=True)
            return
        
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (self.points, button_interaction.user.id))
        cursor.execute("INSERT INTO participants (giveaway_id, user_id) VALUES (?, ?)", (self.giveaway_id, button_interaction.user.id))
        conn.commit()
        logger.info(f"Giveaway {self.prize}: {button_interaction.user.display_name} removed {self.points} from 0.")

        current_time = asyncio.get_event_loop().time()

        async with self.edit_lock:
            if current_time - self.last_edit > 2:
                await self.update_count(button_interaction.message)
            else:
                if self.update_task and not self.update_task.done():
                    self.update_task.cancel()
                self.update_task = asyncio.create_task(self.delayed_update(button_interaction.message))

        await button_interaction.followup.send("Вы успешно участвуете в розыгрыше!", ephemeral=True)

    async def delayed_update(self, message):
        await asyncio.sleep(2)
        async with self.edit_lock:
            await self.update_count(message)

    async def update_count(self, message):
        conn, cursor = get_guild_db(message.guild.id)
        embed = message.embeds[0]
        cursor.execute("SELECT COUNT(*) FROM participants WHERE giveaway_id = ?", (message.id,))
        participant_count = cursor.fetchone()[0]
        embed.set_field_at(index=0, name = "", value=f"Участников: {participant_count}")

        await message.edit(embed=embed)
        self.last_edit = asyncio.get_event_loop().time()  


async def check_active_giveaways(client):
    conn, cursor = get_guild_db(GUILD_ID)
    cursor.execute("SELECT message_id, channel_id, guild_id, prize, points, end_time FROM giveaways")
    active_giveaways = cursor.fetchall()
    active_giveaways.sort(key=lambda x: x[5])
    # Buttons updating
    for giveaway in active_giveaways:
        message_id, channel_id, guild_id, prize, points, end_time = giveaway
        view = View(timeout=None)
        view.add_item(GiveawayButton(message_id, points))
        client.add_view(view)

    return active_giveaways

async def giveaway_end(client, giveaway):
    message_id, channel_id, guild_id, prize, points, end_time = giveaway
    channel = client.get_channel(channel_id)
    message = await channel.fetch_message(message_id)
    await message.edit(view=None)

    conn, cursor = get_guild_db(GUILD_ID)
    cursor.execute("SELECT user_id FROM participants WHERE giveaway_id = ?", (message_id,))
    participants = [row[0] for row in cursor.fetchall()]
    embed = message.embeds[0]
    
    if not participants:
        embed.description = f"**## {prize}**\n**Розыгрыш завершен <t:{end_time}:f>!**"
        embed.set_field_at(0, name="", value=f"Участников: {len(participants)}")
        await message.edit(embed=embed, view=None)
        logger.info(f"Giveaway {prize} ended.")
    else:
        winner_id = random.choice(participants)
        winner = channel.guild.get_member(winner_id)
        winner_name = winner.mention if winner else f"Unknown ({winner_id})"
        embed.description = f"**## {prize}**\n**Розыгрыш завершен <t:{end_time}:f>!\n\nПобедитель: {winner_name}**"
        embed.set_field_at(0, name="", value=f"Участников: {len(participants)}")
        await message.edit(embed=embed, view=None)
        logger.info(f"Giveaway {prize} ended, winner is {winner.display_name}.")
        await message.reply(f"🎉 Поздравляем {winner_name} с победой в розыгрыше! 🎉")
    
    cursor.execute("DELETE FROM giveaways WHERE message_id = ?", (message_id,))
    cursor.execute("DELETE FROM participants WHERE giveaway_id = ?", (message_id,))
    conn.commit()
