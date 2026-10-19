import os
import json
import asyncio
import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# IDs
GUILD_ID = 1491473628439777442
VOICE_CHANNEL_ID = 1561777212670218271
ANNOUNCEMENT_CHANNEL_ID = 1520035262032384050
TRACKED_CHANNELS = [
    1491473823139364894,
    1491504862465097859,
    1491504915191955737,
    1546117963348840590,
]
OWNER_IDS = {1377967442172579843, 909086434340786236}

DATA_FILE = "activity_data.json"


# --- Storage Helpers ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {str(cid): 0 for cid in TRACKED_CHANNELS}
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            for cid in TRACKED_CHANNELS:
                data.setdefault(str(cid), 0)
            return data
    except Exception:
        return {str(cid): 0 for cid in TRACKED_CHANNELS}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def parse_color(color_str: str) -> discord.Color:
    if not color_str:
        return discord.Color.green()
    clean = color_str.strip().lstrip("#")
    try:
        return discord.Color(int(clean, 16))
    except ValueError:
        return discord.Color.green()


# --- Setup Bot ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, status=discord.Status.dnd)
activity_data = load_data()


# Voice Channel Persistent Join Helper
async def join_target_vc():
    """Forces the bot to join or move back into the designated voice channel."""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    vc_channel = guild.get_channel(VOICE_CHANNEL_ID)
    if not vc_channel or not isinstance(vc_channel, discord.VoiceChannel):
        print(f"[VC Warning] Voice channel {VOICE_CHANNEL_ID} not found or invalid.")
        return

    vc = guild.voice_client

    try:
        if vc is None:
            # Not in any channel, connect directly
            await vc_channel.connect(reconnect=True, timeout=15.0, self_deaf=True)
            print(f"[VC] Connected to {vc_channel.name} ({vc_channel.id})")
        elif not vc.is_connected():
            # Voice client exists but is disconnected/stale
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(1)
            await vc_channel.connect(reconnect=True, timeout=15.0, self_deaf=True)
            print(f"[VC] Reconnected to {vc_channel.name} ({vc_channel.id})")
        elif vc.channel.id != VOICE_CHANNEL_ID:
            # In a different VC (e.g. dragged by a user/admin), move back
            await vc.move_to(vc_channel)
            print(f"[VC] Moved back to {vc_channel.name} ({vc_channel.id})")
    except Exception as e:
        print(f"[VC Error] Failed connecting to voice: {e}")


def is_owner_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id in OWNER_IDS:
            return True
        await interaction.response.send_message(
            "❌ Only bot owners can use this command.", ephemeral=True
        )
        return False
    return app_commands.check(predicate)


# --- Modals ---
class ChannelAnnounceModal(discord.ui.Modal, title="Channel Announcement"):
    msg_content = discord.ui.TextInput(
        label="Message Text",
        style=discord.TextStyle.paragraph,
        placeholder="Enter plain message text (optional)...",
        required=False,
        max_length=2000,
    )
    embed_title = discord.ui.TextInput(
        label="Embed Title",
        style=discord.TextStyle.short,
        placeholder="Enter title (optional)...",
        required=False,
        max_length=256,
    )
    embed_content = discord.ui.TextInput(
        label="Embed Content",
        style=discord.TextStyle.paragraph,
        placeholder="Enter embed body...",
        required=False,
        max_length=4000,
    )
    embed_color = discord.ui.TextInput(
        label="Embed Color Hex Code",
        style=discord.TextStyle.short,
        placeholder="#2ecc71 or 2ecc71",
        required=False,
        max_length=7,
    )
    embed_images = discord.ui.TextInput(
        label="Images: Large Image URL | Thumbnail URL",
        style=discord.TextStyle.paragraph,
        placeholder="Line 1: Large Image URL\nLine 2: Thumbnail URL",
        required=False,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        embed = None
        has_embed = any([
            self.embed_title.value,
            self.embed_content.value,
            self.embed_images.value,
        ])

        if has_embed:
            color = parse_color(self.embed_color.value)
            embed = discord.Embed(
                title=self.embed_title.value or None,
                description=self.embed_content.value or None,
                color=color,
            )

            lines = [l.strip() for l in self.embed_images.value.splitlines() if l.strip()]
            if len(lines) >= 1 and lines[0].startswith("http"):
                embed.set_image(url=lines[0])
            if len(lines) >= 2 and lines[1].startswith("http"):
                embed.set_thumbnail(url=lines[1])

        content = self.msg_content.value.strip() or None
        if not content and not embed:
            await interaction.followup.send("⚠️ Cannot send an empty announcement.", ephemeral=True)
            return

        try:
            await interaction.channel.send(content=content, embed=embed)
            await interaction.followup.send("✅ Announcement successfully sent!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to send announcement: {e}", ephemeral=True)


class DirectAnnounceModal(discord.ui.Modal, title="DM Server Announcement"):
    msg_content = discord.ui.TextInput(
        label="Normal Message Box",
        style=discord.TextStyle.paragraph,
        placeholder="Message content sent along with embed (optional)...",
        required=False,
        max_length=2000,
    )
    embed_title = discord.ui.TextInput(
        label="Embed Title",
        style=discord.TextStyle.short,
        placeholder="Title for embed (optional)...",
        required=False,
        max_length=256,
    )
    embed_content = discord.ui.TextInput(
        label="Embed Message Box",
        style=discord.TextStyle.paragraph,
        placeholder="Embed description...",
        required=False,
        max_length=4000,
    )
    embed_color = discord.ui.TextInput(
        label="Embed Color Code",
        style=discord.TextStyle.short,
        placeholder="#2ecc71 or 2ecc71",
        required=False,
        max_length=7,
    )
    embed_images = discord.ui.TextInput(
        label="Images: Large Image URL | Thumbnail URL",
        style=discord.TextStyle.paragraph,
        placeholder="Line 1: Large Image URL\nLine 2: Thumbnail URL",
        required=False,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        embed = None
        has_embed = any([
            self.embed_title.value,
            self.embed_content.value,
            self.embed_images.value,
        ])

        if has_embed:
            color = parse_color(self.embed_color.value)
            embed = discord.Embed(
                title=self.embed_title.value or None,
                description=self.embed_content.value or None,
                color=color,
            )

            lines = [l.strip() for l in self.embed_images.value.splitlines() if l.strip()]
            if len(lines) >= 1 and lines[0].startswith("http"):
                embed.set_image(url=lines[0])
            if len(lines) >= 2 and lines[1].startswith("http"):
                embed.set_thumbnail(url=lines[1])

        content = self.msg_content.value.strip() or None
        if not content and not embed:
            await interaction.followup.send("⚠️ You must provide either content or embed details.", ephemeral=True)
            return

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            await interaction.followup.send("❌ Guild not found.", ephemeral=True)
            return

        await interaction.followup.send("⏳ Broadcast starting in background...", ephemeral=True)

        sent_count = 0
        failed_count = 0

        for member in guild.members:
            if member.bot:
                continue
            try:
                await member.send(content=content, embed=embed)
                sent_count += 1
                await asyncio.sleep(1.2)
            except Exception:
                failed_count += 1

        try:
            await interaction.followup.send(
                f"✅ DM Announcement finished!\n• Successfully sent: **{sent_count}**\n• Failed/DMs closed: **{failed_count}**",
                ephemeral=True,
            )
        except Exception:
            pass


# --- Background Tasks ---
@tasks.loop(seconds=10)
async def ensure_voice_connected():
    """Periodic watchdog to ensure voice connection is maintained."""
    await join_target_vc()


@tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
async def weekly_activity_reset():
    """Runs daily at 00:00 UTC and resets every Sunday midnight."""
    global activity_data
    now = datetime.datetime.now(datetime.timezone.utc)
    if now.weekday() != 6:
        return

    channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        sorted_channels = sorted(activity_data.items(), key=lambda item: item[1], reverse=True)
        top_cid, top_count = sorted_channels[0]
        top_mention = f"<#{top_cid}>"

        embed = discord.Embed(
            title="✨ 𝐖𝐄𝐄𝐊𝐋𝐘 𝐌𝐎𝐒𝐓 𝐀𝐂𝐓𝐈𝐕𝐄 𝐂𝐇𝐀𝐍𝐍𝐄𝐋 ✨",
            description=(
                f"🌿 ━━━━━━━━━━━━━━━━━━━━━ 🌿\n\n"
                f"👑 **Champion of the Week:** {top_mention}\n"
                f"💬 **Total Activity:** `{top_count}` messages\n\n"
                f"✨ *Thank you everyone for keeping the conversations lively and green!* 🍀\n\n"
                f"🌿 ━━━━━━━━━━━━━━━━━━━━━ 🌿"
            ),
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text="Weekly Activity Reset Completed")
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    activity_data = {str(cid): 0 for cid in TRACKED_CHANNELS}
    save_data(activity_data)


# --- Voice State Listener for Instant Rejoining & Anti-Drag ---
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Triggers instantly if the bot itself is disconnected or dragged."""
    if member.id != bot.user.id:
        return

    # If disconnected or moved to another channel
    if after.channel is None or after.channel.id != VOICE_CHANNEL_ID:
        await asyncio.sleep(1)  # Brief pause for Discord to settle the state
        await join_target_vc()


# --- Events ---
@bot.event
async def on_ready():
    await bot.change_presence(
        status=discord.Status.dnd,
        activity=discord.Activity(type=discord.ActivityType.watching, name="discord.gg/owoplace 🍀"),
    )

    # Check and leave unauthorized servers
    for guild in list(bot.guilds):
        if guild.id != GUILD_ID:
            await guild.leave()

    # Join VC immediately
    await join_target_vc()

    if not ensure_voice_connected.is_running():
        ensure_voice_connected.start()

    if not weekly_activity_reset.is_running():
        weekly_activity_reset.start()

    # Sync slash commands with the server
    guild_obj = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild_obj)
    await bot.tree.sync(guild=guild_obj)
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_guild_join(guild: discord.Guild):
    if guild.id != GUILD_ID:
        await guild.leave()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # React with 🍀 if mentioned/pinged
    if bot.user in message.mentions:
        try:
            await message.add_reaction("🍀")
        except Exception:
            pass

    # Count activity in tracked channels
    if message.channel.id in TRACKED_CHANNELS:
        cid_str = str(message.channel.id)
        activity_data[cid_str] = activity_data.get(cid_str, 0) + 1
        save_data(activity_data)

    await bot.process_commands(message)


# --- Slash Commands ---

@bot.tree.command(name="announce", description="Send an announcement via DM to all members (Owners only)")
@is_owner_check()
async def announce(interaction: discord.Interaction):
    await interaction.response.send_modal(DirectAnnounceModal())


@bot.tree.command(name="channel_announce", description="Send an announcement embed into this channel (Owners only)")
@is_owner_check()
async def channel_announce(interaction: discord.Interaction):
    await interaction.response.send_modal(ChannelAnnounceModal())


@bot.tree.command(name="say", description="Send a message in the current channel (Owners only)")
@app_commands.describe(content="Content to send")
@is_owner_check()
async def say(interaction: discord.Interaction, content: str):
    await interaction.channel.send(content)
    await interaction.response.send_message("✅ Sent!", ephemeral=True)


@bot.tree.command(name="dm", description="Send a direct message to a specific user (Owners only)")
@app_commands.describe(user="The user to DM", content="The message content")
@is_owner_check()
async def dm(interaction: discord.Interaction, user: discord.Member, content: str):
    try:
        await user.send(content)
        await interaction.response.send_message(f"✅ DM sent to {user.mention}!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Could not DM {user.mention}: {e}", ephemeral=True)


@bot.tree.command(name="top", description="Check the activity ranking of tracked channels")
async def top(interaction: discord.Interaction):
    medals = ["🥇", "🥈", "🥉", "4️⃣"]
    sorted_channels = sorted(
        TRACKED_CHANNELS,
        key=lambda cid: activity_data.get(str(cid), 0),
        reverse=True,
    )

    lines = []
    for rank, cid in enumerate(sorted_channels):
        pts = activity_data.get(str(cid), 0)
        lines.append(f"{medals[rank]} **Rank {rank + 1}**: <#{cid}> — `{pts}` messages")

    embed = discord.Embed(
        title="🍀 𝐀𝐜𝐭𝐢𝐯𝐢𝐭𝐲 𝐋𝐞𝐚𝐝𝐞𝐫𝐛𝐨𝐚𝐫𝐝",
        description="\n\n".join(lines),
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_footer(text="Resets weekly every Sunday")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="info", description="Display detailed server information")
async def info(interaction: discord.Interaction):
    guild = interaction.guild or bot.get_guild(GUILD_ID)
    if not guild:
        await interaction.response.send_message("❌ Server not found.", ephemeral=True)
        return

    text_count = len(guild.text_channels)
    voice_count = len(guild.voice_channels)
    roles_count = len(guild.roles)
    members_count = guild.member_count or len(guild.members)

    created_timestamp = int(guild.created_at.timestamp())
    created_str = f"<t:{created_timestamp}:F> (<t:{created_timestamp}:R>)"

    owner = guild.owner or (await bot.fetch_user(guild.owner_id) if guild.owner_id else "Unknown")
    owner_str = f"{owner.name}" if hasattr(owner, "name") else str(owner)

    embed = discord.Embed(
        title=f"⚙️ {guild.name}",
        color=discord.Color.green(),
    )

    embed.add_field(name="Name", value=guild.name, inline=True)
    embed.add_field(name="ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="Owner", value=owner_str, inline=True)

    embed.add_field(name="Verification", value=str(guild.verification_level).capitalize(), inline=True)
    embed.add_field(name="Language", value="English (US) 🇺🇸\nTamil (தமிழ்) 🇮🇳", inline=True)
    embed.add_field(name="Members", value=str(members_count), inline=True)

    embed.add_field(name="Text Channels", value=str(text_count), inline=True)
    embed.add_field(name="Voice Channels", value=str(voice_count), inline=True)
    embed.add_field(name="Roles", value=str(roles_count), inline=True)

    embed.add_field(name="Server Created", value=created_str, inline=False)

    emojis = [str(e) for e in guild.emojis]
    if emojis:
        display_emojis = " ".join(emojis[:28])
        if len(emojis) > 28:
            display_emojis += f" +{len(emojis) - 28} more"
        embed.add_field(name=f"Emojis [{len(emojis)}]", value=display_emojis, inline=False)

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    if guild.banner:
        embed.set_image(url=guild.banner.url)

    embed.set_footer(
        text=guild.name,
        icon_url=guild.icon.url if guild.icon else None,
    )

    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN environment variable not set in .env")
    bot.run(TOKEN)
