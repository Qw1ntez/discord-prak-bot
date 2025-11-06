from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
import os
import asyncio
import socket
import sys

# ===== БЛОКИРОВКА ОТ ДУБЛИРОВАНИЯ =====
try:
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lock_socket.bind(('localhost', 47200))
except socket.error:
    print("❌ Бот уже запущен! Завершите предыдущие процессы.")
    sys.exit(1)

# ===== FLASK СЕРВЕР =====
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ===== ИНИЦИАЛИЗАЦИЯ БОТА (ТОЛЬКО ОДИН РАЗ!) =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ===== ПЕРЕМЕННЫЕ ДЛЯ ХРАНЕНИЯ ДАННЫХ =====
active_team_searches = {}
match_requests = {}
search_messages = {}
ACCESS_ROLES = ["Владелец команды", "Заместитель команды", "Капитан команды"]

# ===== КЛАССЫ ДЛЯ КНОПОК =====
class TeamSearchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🎯 Найти прак для команды', style=discord.ButtonStyle.green, custom_id='team_search')
    async def search_team_prak(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ... ваш код кнопки (без изменений) ...
        pass

class TeamMatchView(discord.ui.View):
    def __init__(self, target_team_id):
        super().__init__(timeout=3600)
        self.target_team_id = target_team_id

    @discord.ui.button(label='⚔️ Предложить матч', style=discord.ButtonStyle.blurple)
    async def offer_team_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ... ваш код кнопки (без изменений) ...
        pass

class AcceptTeamMatchView(discord.ui.View):
    def __init__(self, match_id):
        super().__init__(timeout=3600)
        self.match_id = match_id

    @discord.ui.button(label='✅ Принять матч', style=discord.ButtonStyle.green)
    async def accept_team_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ... ваш код кнопки (без изменений) ...
        pass

    @discord.ui.button(label='❌ Отклонить', style=discord.ButtonStyle.red)
    async def decline_team_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ... ваш код кнопки (без изменений) ...
        pass

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
async def update_search_message(team_id, team1, team2):
    # ... ваш код (без изменений) ...
    pass

async def auto_stop_search(team_id, captain, delay_seconds):
    # ... ваш код (без изменений) ...
    pass

# ===== ОБРАБОТЧИКИ СОБЫТИЙ (ТОЛЬКО ОДИН РАЗ КАЖДЫЙ!) =====
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    # РЕГИСТРИРУЕМ КНОПКИ ТОЛЬКО ЗДЕСЬ И ТОЛЬКО ОДИН РАЗ
    bot.add_view(TeamSearchView())

# ===== КОМАНДЫ (ТОЛЬКО ОДИН РАЗ КАЖДАЯ!) =====
@bot.command()
async def поиск(ctx):
    """Команда для поиска прака - ОДИН РАЗ"""
    embed = discord.Embed(
        title="🏆 Система поиска командных праков",
        description=f"Нажми кнопку ниже чтобы начать поиск противника для твоей команды!",
        color=0x0099ff
    )
    embed.add_field(name="🎯 Как это работает:", 
                   value="1. Нажми 'Найти прак для команды'\n2. Другие команды увидят твой поиск\n3. Принимай вызовы от других команд\n4. **Автоостановка через 30 минут**", 
                   inline=False)

    view = TeamSearchView()
    await ctx.send(embed=embed, view=view)

@bot.command()
async def стоп(ctx):
    """Остановить поиск для своей команды - ОДИН РАЗ"""
    user = ctx.author
    user_team_roles = [role for role in user.roles 
                      if role.name not in ACCESS_ROLES 
                      and not role.is_default() 
                      and role.name != "@everyone"]

    stopped = False
    for team_role in user_team_roles:
        if team_role.id in active_team_searches:
            if team_role.id in search_messages:
                try:
                    message_data = search_messages[team_role.id]
                    channel = bot.get_channel(message_data['channel_id'])
                    if channel:
                        message = await channel.fetch_message(message_data['message_id'])
                        embed = discord.Embed(title="⏹️ Поиск остановлен", description="Поиск был остановлен вручную", color=0xffff00)
                        embed.add_field(name="🏆 Команда:", value=team_role.name, inline=True)
                        embed.add_field(name="📊 Статус", value="⏹️ **Остановлено**", inline=True)
                        await message.edit(embed=embed, view=None)
                except:
                    pass
                del search_messages[team_role.id]
            del active_team_searches[team_role.id]
            stopped = True

    if stopped:
        await ctx.send("✅ Поиск для твоей команды остановлен!")
    else:
        await ctx.send("❌ Твоя команда не в поиске!")

@bot.command()
async def команды(ctx):
    """Показать все команды в поиске - ОДИН РАЗ"""
    if not active_team_searches:
        embed = discord.Embed(title="🏆 Активные поиски команд", description="Сейчас нет команд в поиске праков", color=0xff0000)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="🏆 Команды в поиске праков", description=f"Сейчас в поиске **{len(active_team_searches)}** команд:", color=0x00ff00)
        for team_id, search_data in active_team_searches.items():
            team_role = search_data['team_role']
            captain = search_data['captain']
            captain_role = search_data['captain_role']
            time_ago = f"<t:{int(search_data['time'].timestamp())}:R>"
            embed.add_field(name=f"🏆 {captain_role} команды {team_role.name}", value=f"👤 Прак ищет: {captain.mention}\n🏆 Команда: {team_role.name}\n⏰ В поиске: {time_ago}", inline=False)
        await ctx.send(embed=embed)

# ===== ЗАПУСК (ТОЛЬКО ОДИН РАЗ В КОНЦЕ!) =====
keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))
