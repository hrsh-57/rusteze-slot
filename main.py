import discord
from discord import app_commands
from discord.ext import tasks, commands
import configparser
from discord.ui import Modal, TextInput, Select, View
import random
import chat_exporter
import string
import time
import re
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import pytz
from discord.ext import commands
from rich.console import Console
from rich.table import Table
import io
import zipfile
import shutil

config = configparser.ConfigParser()
with open('config.ini', 'r', encoding='utf-8') as f:
    config.read_file(f)

# Add this near your other initialization code
os.makedirs('transcripts', exist_ok=True)

async def on_command_error(ctx, error):
    print(f"Error in command {ctx.command}: {error}")
    pass

class CloseButton(discord.ui.Button):
    def __init__(self, user, staff_role):
        super().__init__(style=discord.ButtonStyle.danger, label="Close Ticket", emoji="🔒", custom_id="close_ticket")
        self.user = user
        self.staff_role = staff_role

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=discord.Embed(
            title="Ticket Closing",
            description="Creating transcript...",
            color=embed_color
        ))

        try:
            # Collect messages
            messages = []
            async for message in interaction.channel.history(limit=None, oldest_first=True):
                # Handle attachments
                saved_attachments = []
                for attachment in message.attachments:
                    # Store direct URL of the attachment
                    is_image = any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp'])
                    saved_attachments.append({
                        'type': 'image' if is_image else 'file',
                        'url': attachment.url,  # Store the direct URL
                        'name': attachment.filename
                    })

                # Store message data
                msg_data = {
                    'timestamp': message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    'author': f"{message.author.name}#{message.author.discriminator}",
                    'content': message.content if message.content else "",
                    'embeds': [],
                    'attachments': saved_attachments
                }

                # Process embeds
                for embed in message.embeds:
                    embed_data = {
                        'title': embed.title if embed.title else "",
                        'description': embed.description if embed.description else "",
                        'color': embed.color.value if embed.color else embed_color,
                        'fields': []
                    }
                    
                    # Add fields
                    for field in embed.fields:
                        embed_data['fields'].append({
                            'name': field.name,
                            'value': field.value,
                            'inline': field.inline
                        })

                    # Add footer if exists
                    if embed.footer:
                        embed_data['footer'] = embed.footer.text

                    # Add thumbnail if exists
                    if embed.thumbnail:
                        embed_data['thumbnail'] = embed.thumbnail.url

                    msg_data['embeds'].append(embed_data)

                messages.append(msg_data)

            # Generate HTML with direct URLs
            transcript = await chat_exporter.export(
                channel=interaction.channel,
                guild=interaction.guild
            )
            # Create HTML file in memory
            html_file = discord.File(
                io.StringIO(transcript),
                filename=f'transcript-{interaction.channel.name}.html'
            )

            # Send transcript to channels
            transcript_channel_id = int(config['Logging']['TranscriptChannelID'])
            transcript_channel = interaction.guild.get_channel(transcript_channel_id)

            if transcript_channel:
                transcript_embed = discord.Embed(
                    title="Ticket Transcript",
                    description="Ticket has been closed and transcript saved.",
                    color=embed_color,
                    timestamp=datetime.now(timezone.utc)
                )
                transcript_embed.add_field(name="Ticket", value=interaction.channel.name, inline=True)
                transcript_embed.add_field(name="Closed By", value=interaction.user.mention, inline=True)
                transcript_embed.add_field(name="Created By", value=self.user.mention, inline=True)
                transcript_embed.set_footer(text=embed_footer)

                await transcript_channel.send(
                    embed=transcript_embed,
                    file=html_file
                )

                # Send to user in DM
                try:
                    user_embed = discord.Embed(
                        title="Ticket Transcript",
                        description="Your ticket has been closed. Here's a transcript of the conversation.",
                        color=embed_color,
                        timestamp=datetime.now(timezone.utc)
                    )
                    user_embed.set_footer(text=embed_footer)
                    
                    # Create a new file object for DM
                    dm_html_file = discord.File(
                        io.StringIO(transcript),
                        filename=f'transcript-{interaction.channel.name}.html'
                    )
                    
                    await self.user.send(
                        embed=user_embed,
                        file=dm_html_file
                    )
                except discord.Forbidden:
                    print(f"Could not send transcript to user {self.user.name} - DMs closed")
                except Exception as e:
                    print(f"Error sending transcript to user: {e}")

            # Wait 5 seconds before closing
            await asyncio.sleep(5)
            await interaction.channel.delete()

        except Exception as e:
            error_embed = discord.Embed(
                title="Error",
                description=f"An error occurred while creating the transcript: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.channel.send(embed=error_embed)

slots_data_file = 'slots_data.json'
ping_data_file = 'ping.json'
keys_file = 'keys_data.json'

bot_token = config['Bot']['Token']
bot_status = config['Bot']['Status']
bot_role_id = int(config['Bot']['RoleID'])
server_id = int(config['Bot']['ServerID'])
seller_channelID = int(config['Bot']['seller_channelID'])

log_channel_id = int(config['Logging']['LogChannelID'])

embed_color = int(config['Embed']['Color'], 16)  
embed_footer = config['Embed']['Footer']
embed_thumbnail_url = config['Embed']['ThumbnailURL']

category1_id = int(config['Categories']['Category1ID'])
category2_id = int(config['Categories']['Category2ID'])
category3_id = int(config['Categories']['Category3ID'])

cat_1_premium_role_id = int(config['Roles']['Cat1PremiumRoleID'])
cat_2_premium_role_id = int(config['Roles']['Cat2PremiumRoleID'])
cat_3_premium_role_id = int(config['Roles']['Cat3PremiumRoleID'])

TIMEZONE = config['Reset']['Timezone']
RESET_HOUR = int(config['Reset']['Hour'])
RESET_MINUTE = int(config['Reset']['Minute'])

# Initialize rich console for better output
console = Console()

ascii_art = ""

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

@bot.event
async def on_ready():    
    os.system("cls" if os.name == "nt" else "clear")
    bot.loop.create_task(sync_commands())    
    await ping_reset.start()# Clear console first
    console.print(ascii_art)  # Print ASCII Art instantly

    # Add persistent views
    bot.add_view(discord.ui.View(timeout=None))  # For existing panel messages
    
    # Register persistent view for PurchaseButton
    purchase_view = discord.ui.View(timeout=None)
    purchase_view.add_item(PurchaseButton())
    bot.add_view(purchase_view)
    class PersistentCloseButton(discord.ui.Button):
        def __init__(self):
            super().__init__(
                style=discord.ButtonStyle.danger,
                label="Close Ticket", 
                emoji="🔒",
                custom_id="close_ticket"  # Add custom_id for persistence
            )
            
        async def callback(self, interaction: discord.Interaction):
            # Find the user who created the ticket and the staff role
            try:
                channel_name = interaction.channel.name
                user = None
                
                # Try to extract username from channel name
                if channel_name.startswith("slotbuy-"):
                    user_name = channel_name.replace("slotbuy-", "")
                    user = discord.utils.get(interaction.guild.members, name=user_name)
                
                # If user not found, fallback to interaction user
                if not user:
                    user = interaction.user
                    
                # Get staff role
                staff_role = discord.utils.get(interaction.guild.roles, id=bot_role_id)
                
                # Create a new CloseButton with the correct parameters
                close_button = CloseButton(user, staff_role)
                # Call its callback
                await close_button.callback(interaction)
            except Exception as e:
                await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)
    
    close_view = discord.ui.View(timeout=None)
    close_view.add_item(PersistentCloseButton())
    bot.add_view(close_view)
    
    # Sync commands in the background

    # Update presence
    await bot.change_presence(activity=discord.Game(name=".gg/mikoxn"))

    # Small delay for smooth console update
    await asyncio.sleep(1)
    await update_console()  # Call as async since it interacts with bot.user

async def sync_commands():
    await bot.tree.sync()
    console.print("[bold green]Commands Synced! ✅[/bold green]")

async def update_console():
    os.system("cls" if os.name == "nt" else "clear")
    console.print(ascii_art)

    # Get the server name (assuming the bot is in only one server)
    guild = bot.guilds[0] if bot.guilds else None
    server_name = guild.name if guild else "Unknown"

    # Styled table output
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Setting", style="bold yellow", justify="center", width=25)
    table.add_column("Status", style="bold green", justify="center", width=30)

    table.add_row("Bot Name", bot.user.name)
    table.add_row("Server", server_name)  # Display the actual server name
    table.add_row("Developer", "spythen")
    table.add_row("Support Server", ".gg/hellmp")  # Display the actual server name

    console.print(table)

    # Ensure bot.user is available before accessing it
    if bot.user:
        console.print(f"[bold green]Logged in as:[/bold green] {bot.user.name} ({bot.user.id})")
    else:
        console.print("[bold red]Bot user not available![/bold red]")

def load_json_data(file_path):
    if not os.path.exists(file_path):
        return {}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_data(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
@bot.command()
async def create(ctx, user_mention: discord.Member, category_number: int, duration: str, here_ping: int, everyone_ping: int, image_url: str = None):
    await ctx.message.delete()
    role = discord.utils.get(ctx.guild.roles, id=bot_role_id)
    if role not in ctx.author.roles:
        await ctx.send("You do not have the required role to use this command.", delete_after=5)
        return
    if user_mention not in ctx.guild.members:
        await ctx.send("The mentioned user is not in the server.", delete_after=5)
        return
    if category_number not in [1, 2, 3]:
        await ctx.send("Invalid category number. Choose 1,2 or 3.", delete_after=5)
        return
    if not re.match(r'^\d+[dwm]|lifetime$', duration):
        await ctx.send("Invalid duration format. Use 'Xd', 'Xw', 'Xm' or 'lifetime'.", delete_after=5)
        return
    if here_ping < 0 or everyone_ping < 0:
        await ctx.send("Ping limits cannot be negative.", delete_after=5)
        return
    slot_data = load_json_data(slots_data_file)
    if any(slot["user_id"] == user_mention.id for slot in slot_data.values()):
        await ctx.send(f"{user_mention.mention} already has an existing slot. A new slot cannot be created.", delete_after=5)
        return
    # Determine category ID
    if category_number == 1:
        category_id = category1_id
    elif category_number == 2:
        category_id = category2_id
    elif category_number == 3:
        category_id = category3_id
    else:
        await ctx.send("Invalid category number. Choose 1, 2 or 3.", delete_after=5)
        return
    category = discord.utils.get(ctx.guild.categories, id=category_id)
    if not category:
        await ctx.send("Category not found.", delete_after=5)
        return
    # Calculate end time based on duration
    if duration == 'lifetime':
        end_time = None
    else:
        duration_days = int(duration[:-1]) if duration[:-1].isdigit() else 0
        if duration.endswith('d'):
            end_time = datetime.now() + timedelta(days=duration_days)
        elif duration.endswith('w'):
            end_time = datetime.now() + timedelta(weeks=duration_days)
        elif duration.endswith('m'):
            end_time = datetime.now() + timedelta(days=duration_days * 30)
        else:
            await ctx.send("Invalid duration format.", delete_after=5)
            return
    # Prepare data for the new slot
    creation_time = datetime.now()
    end_timestamp = int(end_time.timestamp()) if end_time else None
    creation_timestamp = int(creation_time.timestamp())
    channel_name = f"〞♡・{user_mention.name}"
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
        user_mention: discord.PermissionOverwrite(read_messages=True, send_messages=True, mention_everyone=True),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    # Create the text channel for the slot
    channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)
    if channel.category_id == category1_id:
        premium_role_id = cat_1_premium_role_id
    elif channel.category_id == category2_id:
        premium_role_id = cat_2_premium_role_id
    elif channel.category_id == category3_id:
        premium_role_id = cat_3_premium_role_id
    else:
        premium_role_id = None   
    premium_role = discord.utils.get(ctx.guild.roles, id=premium_role_id)
    if premium_role:
        await user_mention.add_roles(premium_role)    
    # Prepare slot data
        # Prepare slot data
        new_slot = {
            "channel_id": channel.id,
            "user_id": user_mention.id,
            "category_id": category_number,
            "duration_days": duration_days if end_time else 'lifetime',
            "end_timestamp": end_timestamp,
            "creation_timestamp": creation_timestamp,
            "here_ping": here_ping,
            "status": "active",
            "everyone_ping": everyone_ping,
            "moderator_id": ctx.author.id,
            "moderator_name": ctx.author.name
        }

        # Store the new slot data
        slot_data[channel.id] = new_slot
        save_json_data(slots_data_file, slot_data)

        # Update ping data
        ping_data = load_json_data(ping_data_file)
        ping_data[user_mention.id] = {
            "allowed_here_ping": here_ping,
            "allowed_everyone_ping": everyone_ping,
            "used_here_ping": 0,
            "used_everyone_ping": 0
        }
        save_json_data(ping_data_file, ping_data)

        # Log the creation of the slot
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            log_embed = discord.Embed(title="Slot Created", color=embed_color)
            log_embed.add_field(name="Channel", value=channel.mention, inline=False)
            log_embed.add_field(name="User ", value=user_mention.mention, inline=False)
            log_embed.add_field(name="Duration", value=f"{duration_days} days" if end_time else "Lifetime", inline=False)
            log_embed.add_field(name="Category", value=category.name, inline=False)
            log_embed.add_field(name="@here Pings Allowed", value=str(here_ping), inline=False)
            log_embed.add_field(name="@everyone Pings Allowed", value=str(everyone_ping), inline=False)
            log_embed.add_field(name="Creation Date", value=f"<t:{creation_timestamp}:R>", inline=False)
            log_embed.add_field(name="Expiry Date", value=f"<t:{end_timestamp}:R>" if end_time else "Lifetime", inline=False)
            log_embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
            log_embed.set_footer(text=embed_footer)
            await log_channel.send(embed=log_embed)
        
        # Notify the user
        user_embed = discord.Embed(title="Your Slot Has Been Created!", color=embed_color)
        user_embed.add_field(name="Channel", value=channel.mention, inline=False)
        user_embed.add_field(name="Duration", value=f"{duration_days} days" if end_time else "Lifetime", inline=False)
        user_embed.add_field(name="Category", value=category.name, inline=False)
        user_embed.add_field(name="@here Pings Allowed", value=str(here_ping), inline=False)
        user_embed.add_field(name="@everyone Pings Allowed", value=str(everyone_ping), inline=False)
        user_embed.add_field(name="Creation Date", value=f"<t:{creation_timestamp}:R>", inline=False)
        user_embed.add_field(name="Expiry Date", value=f"<t:{end_timestamp}:R>" if end_time else "Lifetime", inline=False)
        user_embed.set_footer(text=embed_footer)
        
        await user_mention.send(embed=user_embed)
        
        # Send slot information to the channel
        channel_embed = discord.Embed(title="💠 Slot Information", color=embed_color)
        channel_embed.add_field(name="👑 Slot Owner", value=user_mention.mention, inline=False)
        channel_embed.add_field(name="⌚ Duration", value=f"{duration_days} days" if end_time else "Lifetime", inline=False)
        channel_embed.add_field(name="🥝 Category", value=category.name, inline=False)
        channel_embed.add_field(name="⏰ Creation Date", value=f"<t:{creation_timestamp}:R>", inline=True)
        channel_embed.add_field(name="⌛ Expiry Date", value=f"<t:{end_timestamp}:R>" if end_time else "Lifetime", inline=True)
        channel_embed.add_field(name="📍 Ping Allowed", value=f"{str(everyone_ping)}x @everyone\n{str(here_ping)}x @here", inline=False)
        channel_embed.set_image(url=image_url or embed_thumbnail_url)
        channel_embed.set_thumbnail(url=user_mention.avatar.url if user_mention.avatar else None)        
        channel_embed.set_footer(text=embed_footer)
        
        await channel.send(embed=channel_embed)
        await ctx.send(f"Slot created successfully for {user_mention.mention} in {channel.mention}.", delete_after=30)

@bot.command(name="myslot")
async def my_slot(ctx):
    """Show your slot channel"""
    user = ctx.author
    slot_data = load_json_data(slots_data_file)
    
    # Find user's slot
    user_slot = None
    for slot_id, slot in slot_data.items():
        if slot.get("user_id") == user.id:
            user_slot = slot
            break
    
    if not user_slot:
        await ctx.send(f"❌ {user.mention}, you don't have an active slot.")
        return
    
    # Get channel
    channel_id = user_slot.get("channel_id")
    channel = ctx.guild.get_channel(channel_id)
    
    if channel:
        await ctx.send(f"🔔 {user.mention}, your slot channel: {channel.mention}")
    else:
        await ctx.send(f"❌ {user.mention}, your slot channel not found.")

@bot.command(name="free")
async def free_slot(ctx, user_mention: discord.Member, category_number: int, duration: str, image_url: str = None):
    """Create a FREE slot for a user (2 @here pings, 0 @everyone pings)"""
    await ctx.message.delete()
    role = discord.utils.get(ctx.guild.roles, id=bot_role_id)
    if role not in ctx.author.roles:
        await ctx.send("You do not have the required role to use this command.", delete_after=5)
        return
    
    # Call the create command with free slot settings
    await create(ctx, user_mention, category_number, duration, 2, 0, image_url)

@bot.command(name="paid")
async def paid_slot(ctx, user_mention: discord.Member, category_number: int, duration: str, image_url: str = None):
    """Create a PAID slot for a user (2 @here pings, 1 @everyone ping)"""
    await ctx.message.delete()
    role = discord.utils.get(ctx.guild.roles, id=bot_role_id)
    if role not in ctx.author.roles:
        await ctx.send("You do not have the required role to use this command.", delete_after=5)
        return
    
    # Call the create command with paid slot settings
    await create(ctx, user_mention, category_number, duration, 2, 1, image_url)
@bot.tree.command(name="help", description="List all available commands.")
async def help_command(interaction: discord.Interaction):
    await interaction.response.defer()
    help_embed = discord.Embed(title="Hell MP | Sloty bot", color=embed_color)
    help_embed.set_footer(text=embed_footer)
    commands_list = [
        ("`/create_slot`", "Create a slot with advanced options."),
        ("`/pingupdate`", "Update the allowed @here and @everyone pings for a user."),
        ("`/hold`", "Put a slot on hold with a reason."),
        ("`/unhold`", "Remove the hold from a slot."),
        ("`/revoke`", "Revoke a slot with a reason."),
        ("`/nuke`", "Nuke a slot channel and recreate it."),
        ("`/transfer`", "Transfer slot ownership from one user to another."),
        ("`/redeem`", "Redeem a key for a slot."),
        ("`/slot-info`", "View details of a slot."),
        ("`/recovery`", "Recover channels by deleting old ones and creating new ones for each slot user."),
        ("`/reset-pings`", "Manually reset ping data for all users."),
        ("`/delete`", "Delete all revoked slots and their details."),
        ("`/panel`", "Slot Tiers Information & Ticket Panel."),
    ]
    for command, description in commands_list:
        help_embed.add_field(name=command, value=description, inline=False)
    await interaction.followup.send(embed=help_embed)

# ===== PASTE ALL SLASH COMMANDS HERE =====
# (create_slot, pingupdate, hold, unhold, revoke, nuke, transfer, redeem, generate, renew, slot-info, recovery, slot-ping, reset-pings, delete, panel)

# ===== TICKET SYSTEM COMMANDS =====
# (All ticket-related commands will go here)

# ===== TASKS =====
@tasks.loop(minutes=5)
async def check_expired_slots():
    try:
        slot_data = load_json_data(slots_data_file)
        current_time = datetime.now(timezone.utc)
        for slot_id, slot in list(slot_data.items()):
            if slot.get("status") != "active":
                continue
            end_timestamp = slot.get("end_timestamp")
            if end_timestamp is None:
                continue
            end_time = datetime.fromtimestamp(end_timestamp, tz=timezone.utc)
            if current_time >= end_time:
                user_id = slot["user_id"]
                guild = bot.get_guild(server_id)
                if not guild:
                    continue
                user = guild.get_member(user_id)
                if not user:
                    continue
                # Remove all category premium roles
                premium_role_ids = [cat_1_premium_role_id, cat_2_premium_role_id, cat_3_premium_role_id]
                for role_id in premium_role_ids:
                    role = discord.utils.get(guild.roles, id=role_id)
                    if role and role in user.roles:
                        try:
                            await user.remove_roles(role)
                        except Exception as e:
                            print(f"Failed to remove role {role.name} from {user}: {e}")
                            continue
                slot["status"] = "expired"
                save_json_data(slots_data_file, slot_data)
                try:
                    user_dm_embed = discord.Embed(
                        title="Your Slot Has Expired",
                        description="Your slot has expired. The premium roles have been removed.",
                        color=embed_color
                    )
                    user_dm_embed.set_footer(text="You can purchase a new slot to regain access.")
                    await user.send(embed=user_dm_embed)
                except discord.Forbidden:
                    pass
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    log_embed = discord.Embed(
                        title="Slot Expired",
                        description="A slot has expired and all associated premium roles have been removed.",
                        color=embed_color
                    )
                    log_embed.add_field(name="User", value=user.mention, inline=False)
                    log_embed.add_field(name="Channel ID", value=slot["channel_id"], inline=False)
                    log_embed.set_footer(text="Automatic expiration")
                    await log_channel.send(embed=log_embed)
    except Exception as e:
        print(f"Error in check_expired_slots: {e}")

@check_expired_slots.before_loop
async def before_check_expired_slots():
    await bot.wait_until_ready()
    check_expired_slots.start()

# ===== PING RESET TASK =====
has_reset_today = False
@tasks.loop(minutes=1)
async def ping_reset():
    global has_reset_today
    current_time = datetime.now(pytz.timezone(TIMEZONE))
    hour = current_time.hour
    minute = current_time.minute
    if hour == RESET_HOUR and minute == RESET_MINUTE:
        if not has_reset_today:
            print("[RESET] Time matched. Resetting ping data...")
            try:
                with open(ping_data_file, "r") as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = {}
            for ping_data in data.values():
                ping_data["used_here_ping"] = 0
                ping_data["used_everyone_ping"] = 0
            with open(ping_data_file, "w") as f:
                json.dump(data, f, indent=2)
            guild = bot.get_guild(server_id)
            if guild:
                channel = guild.get_channel(seller_channelID)
                if channel:
                    embed = discord.Embed(
                        title="Ping Data Reset",
                        description="All used pings have been automatically reset to 0.",
                        color=embed_color
                    )
                    embed.set_footer(text=embed_footer)
                    embed.set_thumbnail(url=embed_thumbnail_url)
                    await channel.send(embed=embed)
                    print("[RESET] Embed sent successfully.")
                else:
                    print("[ERROR] Seller channel not found.")
            else:
                print("[ERROR] Guild not found.")
            has_reset_today = True
    else:
        has_reset_today = False

# ===== BOT RUN =====
bot.run(bot_token)
