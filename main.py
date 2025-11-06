from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
import os
import asyncio

# Создаем Flask сервер для мониторинга
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ИНИЦИАЛИЗАЦИЯ БОТА (ТОЛЬКО ОДИН РАЗ!)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Хранилище активных поисков (по ID команды)
active_team_searches = {}
match_requests = {}
search_messages = {}

# Роли которые дают доступ к поиску
ACCESS_ROLES = ["Владелец команды", "Заместитель команды", "Капитан команды"]

class TeamSearchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🎯 Найти прак для команды', style=discord.ButtonStyle.green, custom_id='team_search')
    async def search_team_prak(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        # Проверяем есть ли у пользователя одна из доступных ролей
        has_access_role = any(discord.utils.get(user.roles, name=role_name) for role_name in ACCESS_ROLES)
        if not has_access_role:
            roles_list = ", ".join([f"**{role}**" for role in ACCESS_ROLES])
            await interaction.response.send_message(
                f"❌ Ты должен иметь одну из ролей: {roles_list} чтобы искать праки!",
                ephemeral=True
            )
            return

        # Ищем ВТОРУЮ роль (не системную) для названия команды
        team_roles = [role for role in user.roles 
                     if role.name not in ACCESS_ROLES 
                     and not role.is_default() 
                     and role.name != "@everyone"
                     and not any(keyword in role.name.lower() for keyword in ['admin', 'модератор', 'moderator', 'staff'])]

        if not team_roles:
            await interaction.response.send_message(
                f"❌ У тебя должна быть вторая роль с названием команды (например: Navi, Virtus.pro и т.д.)!",
                ephemeral=True
            )
            return

        # Берем первую подходящую роль как название команды
        team_name_role = team_roles[0]

        # Проверяем не ищет ли уже эта команда
        if team_name_role.id in active_team_searches:
            await interaction.response.send_message(
                "❌ Твоя команда уже в поиске прака!",
                ephemeral=True
            )
            return

        # Определяем тип пользователя (Владелец/Заместитель/Капитан)
        user_role_type = "Игрок"
        for role_name in ACCESS_ROLES:
            if discord.utils.get(user.roles, name=role_name):
                user_role_type = role_name
                break

        # Используем цвет роли команды, или стандартный зеленый если цвета нет
        team_color = team_name_role.color if team_name_role.color.value != 0 else 0x00ff00

        # Добавляем команду в поиск
        active_team_searches[team_name_role.id] = {
            'team_role': team_name_role,
            'captain': user,
            'captain_role': user_role_type,
            'time': discord.utils.utcnow(),
            'channel_id': interaction.channel.id,
            'team_color': team_color
        }

        # Создаем embed для поиска команды с цветом роли
        embed = discord.Embed(
            title="🏆 Команда в поиске прака!",
            description=f"**{user_role_type} команды {team_name_role.name}** ищет противника для прака",
            color=team_color
        )

        embed.add_field(name="👤 Прак ищет:", value=user.mention, inline=True)
        embed.add_field(name="🏆 Команда:", value=team_name_role.name, inline=True)
        embed.add_field(name="⏰ В поиске с", value=f"<t:{int(discord.utils.utcnow().timestamp())}:R>", inline=False)
        embed.add_field(name="⏱️ Автоостановка", value="Через 30 минут", inline=True)
        embed.add_field(name="📊 Статус", value="🔍 **В поиске**", inline=True)

        # Добавляем цветной индикатор
        if team_name_role.color.value != 0:
            color_hex = f"#{team_name_role.color.value:06x}"
            embed.add_field(name="🎨 Цвет команды", value=color_hex.upper(), inline=True)

        view = TeamMatchView(team_name_role.id)

        # Отправляем сообщение и сохраняем его ID
        await interaction.response.send_message(
            embed=embed,  # УБРАЛ ДУБЛИРУЮЩЕЕ СООБЩЕНИЕ
            view=view
        )

        # Сохраняем ID сообщения и канала для этой команды
        original_message = await interaction.original_response()
        search_messages[team_name_role.id] = {
            'message_id': original_message.id,
            'channel_id': interaction.channel.id
        }

        # Запускаем таймер автоостановки
        asyncio.create_task(auto_stop_search(team_name_role.id, user, 1800))

class TeamMatchView(discord.ui.View):
    def __init__(self, target_team_id):
        super().__init__(timeout=3600)
        self.target_team_id = target_team_id

    @discord.ui.button(label='⚔️ Предложить матч', style=discord.ButtonStyle.blurple)
    async def offer_team_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        challenger = interaction.user

        # Проверяем есть ли у вызывающего одна из доступных ролей
        has_access_role = any(discord.utils.get(challenger.roles, name=role_name) for role_name in ACCESS_ROLES)
        if not has_access_role:
            roles_list = ", ".join([f"**{role}**" for role in ACCESS_ROLES])
            await interaction.response.send_message(
                f"❌ Ты должен иметь одну из ролей: {roles_list} чтобы предлагать матчи!",
                ephemeral=True
            )
            return

        # Ищем вторую роль для названия команды
        challenger_team_roles = [role for role in challenger.roles 
                                if role.name not in ACCESS_ROLES 
                                and not role.is_default() 
                                and role.name != "@everyone"
                                and not any(keyword in role.name.lower() for keyword in ['admin', 'модератор', 'moderator', 'staff'])]

        if not challenger_team_roles:
            await interaction.response.send_message(
                f"❌ У тебя должна быть вторая роль с названием команды!",
                ephemeral=True
            )
            return

        challenger_team_role = challenger_team_roles[0]

        # Получаем информацию о целевой команде
        target_team = active_team_searches.get(self.target_team_id)
        if not target_team:
            await interaction.response.send_message("❌ Команда больше не в поиске", ephemeral=True)
            return

        # Проверяем чтобы команда не предлагала матч самой себе
        if challenger_team_role.id == self.target_team_id:
            await interaction.response.send_message("❌ Нельзя предложить матч своей же команде!", ephemeral=True)
            return

        # Определяем тип роли challenger
        challenger_role_type = "Игрок"
        for role_name in ACCESS_ROLES:
            if discord.utils.get(challenger.roles, name=role_name):
                challenger_role_type = role_name
                break

        # Используем цвет роли команды challenger для предложения матча
        challenger_team_color = challenger_team_role.color if challenger_team_role.color.value != 0 else 0xffff00

        # Создаем запрос на матч
        match_id = f"{challenger_team_role.id}_{self.target_team_id}"
        match_requests[match_id] = {
            'challenger_team': challenger_team_role,
            'challenger_captain': challenger,
            'challenger_role_type': challenger_role_type,
            'challenger_team_color': challenger_team_color,
            'target_team': target_team['team_role'],
            'target_captain': target_team['captain'],
            'target_channel_id': target_team['channel_id'],
            'target_team_color': target_team['team_color'],
            'time': discord.utils.utcnow()
        }

        # Уведомляем капитана целевой команды
        target_captain = target_team['captain']

        embed = discord.Embed(
            title="🏆 Предложение командного матча!",
            description=f"**{challenger_role_type} команды {challenger_team_role.name}** предлагает вашей команде **{target_team['team_role'].name}** сыграть прак!",
            color=challenger_team_color
        )
        embed.add_field(name="👤 Прак ищет:", value=challenger.mention, inline=True)
        embed.add_field(name="🏆 Их команда:", value=challenger_team_role.name, inline=True)

        accept_view = AcceptTeamMatchView(match_id)

        try:
            await target_captain.send(embed=embed, view=accept_view)
            await interaction.response.send_message(
                f"✅ Предложение матча отправлено {target_team['captain_role'].lower()}у {target_captain.mention}!",
                ephemeral=True
            )
        except:
            await interaction.response.send_message(
                f"❌ Не удалось отправить предложение. У {target_team['captain_role'].lower()}а {target_captain.display_name} закрыты ЛС?",
                ephemeral=True
            )

class AcceptTeamMatchView(discord.ui.View):
    def __init__(self, match_id):
        super().__init__(timeout=3600)
        self.match_id = match_id

    @discord.ui.button(label='✅ Принять матч', style=discord.ButtonStyle.green)
    async def accept_team_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Получаем данные матча
        match_data = match_requests.get(self.match_id)
        if not match_data:
            await interaction.response.send_message("❌ Предложение матча устарело или было отменено", ephemeral=True)
            return

        challenger_team = match_data['challenger_team']
        target_team = match_data['target_team']
        challenger_captain = match_data['challenger_captain']
        target_channel_id = match_data['target_channel_id']

        # Удаляем команды из активного поиска
        if challenger_team.id in active_team_searches:
            del active_team_searches[challenger_team.id]
        if target_team.id in active_team_searches:
            del active_team_searches[target_team.id]

        # Удаляем запрос матча
        del match_requests[self.match_id]

        # Обновляем сообщения поиска
        await update_search_message(challenger_team.id, target_team, challenger_team)
        await update_search_message(target_team.id, target_team, challenger_team)

        # Отправляем уведомление в ЛС
        embed = discord.Embed(
            title="🎉 Командный матч назначен!",
            description=f"**Команды договорились о праке!**",
            color=0x00ff00
        )
        embed.add_field(name="🏆 Участники:", 
                       value=f"**{challenger_team.name}** 🆚 **{target_team.name}**", 
                       inline=False)
        embed.add_field(name="👤 Договорились:", 
                       value=f"{challenger_captain.mention} 🆚 {interaction.user.mention}", 
                       inline=False)
        embed.add_field(name="🎯 Следующие шаги:", 
                       value="• Договоритесь о времени через ЛС\n• Подготовьте составы команд\n• Удачи в игре!", 
                       inline=False)

        try:
            await challenger_captain.send(embed=embed)
        except:
            pass

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label='❌ Отклонить', style=discord.ButtonStyle.red)
    async def decline_team_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        match_data = match_requests.get(self.match_id)
        if match_data:
            challenger_captain = match_data['challenger_captain']
            challenger_team = match_data['challenger_team']
            del match_requests[self.match_id]

            try:
                await challenger_captain.send(f"❌ {interaction.user.display_name} отклонил предложение матча от команды {challenger_team.name}")
            except:
                pass

        await interaction.response.send_message("❌ Предложение матча отклонено", ephemeral=True)

async def update_search_message(team_id, team1, team2):
    """Обновляет сообщение поиска когда матч найден"""
    if team_id in search_messages:
        try:
            message_data = search_messages[team_id]
            channel = bot.get_channel(message_data['channel_id'])
            if channel:
                message = await channel.fetch_message(message_data['message_id'])

                embed = discord.Embed(
                    title="✅ Прак найден!",
                    description="Матч успешно организован",
                    color=0x00ff00
                )

                embed.add_field(name="🏆 Участвующие команды:", 
                              value=f"**{team1.name}** 🆚 **{team2.name}**", 
                              inline=False)
                embed.add_field(name="📊 Статус", value="✅ **Найдено**", inline=True)
                embed.add_field(name="⏰ Время найма", value=f"<t:{int(discord.utils.utcnow().timestamp())}:R>", inline=True)

                await message.edit(embed=embed, view=None)

            del search_messages[team_id]

        except Exception as e:
            print(f"Ошибка при обновлении сообщения: {e}")

async def auto_stop_search(team_id, captain, delay_seconds):
    """Автоматически останавливает поиск через указанное время"""
    await asyncio.sleep(delay_seconds)

    if team_id in active_team_searches:
        team_data = active_team_searches[team_id]
        del active_team_searches[team_id]

        if team_id in search_messages:
            try:
                message_data = search_messages[team_id]
                channel = bot.get_channel(message_data['channel_id'])
                if channel:
                    message = await channel.fetch_message(message_data['message_id'])

                    embed = discord.Embed(
                        title="⏰ Поиск остановлен",
                        description="Время поиска истекло",
                        color=0xff0000
                    )
                    embed.add_field(name="🏆 Команда:", value=team_data['team_role'].name, inline=True)
                    embed.add_field(name="📊 Статус", value="❌ **Время вышло**", inline=True)
                    embed.add_field(name="⏱️ Длительность", value="30 минут", inline=True)

                    await message.edit(embed=embed, view=None)

            except:
                pass

            del search_messages[team_id]

        try:
            await captain.send(f"⏰ **Поиск автоматически остановлен**\nК сожалению, за 30 минут не нашлось противника для команды **{team_data['team_role'].name}**.\nПопробуй начать поиск снова!")
        except:
            pass

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    bot.add_view(TeamSearchView())

@bot.command()
async def поиск(ctx):
    """Команда для поиска прака"""
    embed = discord.Embed(
        title="🏆 Система поиска командных праков",
        description=f"Нажми кнопку ниже чтобы начать поиск противника для твоей команды!\n\n**Требования:**\n• Одна из ролей: {', '.join([f'**{role}**' for role in ACCESS_ROLES])}\n• Вторая роль с названием команды",
        color=0x0099ff
    )
    embed.add_field(name="🎯 Как это работает:", 
                   value="1. Нажми 'Найти прак для команды'\n2. Другие команды увидят твой поиск\n3. Принимай вызовы от других команд\n4. **Автоостановка через 30 минут**", 
                   inline=False)

    view = TeamSearchView()
    await ctx.send(embed=embed, view=view)

@bot.command()
async def стоп(ctx):
    """Остановить поиск для своей команды"""
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

                        embed = discord.Embed(
                            title="⏹️ Поиск остановлен",
                            description="Поиск был остановлен вручную",
                            color=0xffff00
                        )
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
    """Показать все команды в поиске"""
    if not active_team_searches:
        embed = discord.Embed(
            title="🏆 Активные поиски команд",
            description="Сейчас нет команд в поиске праков",
            color=0xff0000
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="🏆 Команды в поиске праков",
            description=f"Сейчас в поиске **{len(active_team_searches)}** команд:",
            color=0x00ff00
        )

        for team_id, search_data in active_team_searches.items():
            team_role = search_data['team_role']
            captain = search_data['captain']
            captain_role = search_data['captain_role']
            time_ago = f"<t:{int(search_data['time'].timestamp())}:R>"

            team_color = search_data['team_color']

            embed.add_field(
                name=f"🏆 {captain_role} команды {team_role.name}",
                value=f"👤 Прак ищет: {captain.mention}\n🏆 Команда: {team_role.name}\n⏰ В поиске: {time_ago}",
                inline=False
            )

        await ctx.send(embed=embed)

# ЗАПУСК ВСЕГО
keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))
