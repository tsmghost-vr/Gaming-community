import discord
from discord.ext import commands
import asyncio
import json
import os

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix=None, intents=intents)

# ===== CONFIG =====
GUILD_ID = 1449139074605518880
LOBBY_VC_IDS = [1449139075465482263]
TEMP_CATEGORY_ID = 1449139868339929088
INTERFACE_CATEGORY_ID = 1449139075465482261
TEMP_PREFIX = "Temp"
AUTO_DELETE_DELAY = 5
JSON_FILE = "vc_data.json"
# ==================

# --- Global variables ---
temp_channels = {}
interface_channels = {}
vc_join_order = {}
user_vc_names = {}
vc_data = {}
# =========================

# Load JSON if exists
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r") as f:
        data = json.load(f)
        user_vc_names = data.get("user_vc_names", {})
        vc_data = data.get("vc_data", {})

def save_json():
    with open(JSON_FILE, "w") as f:
        json.dump({"user_vc_names": user_vc_names, "vc_data": vc_data}, f, indent=4)

# ---------- Modals ----------
class RenameModal(discord.ui.Modal, title="Rename your temp channel"):
    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc
        self.name_input = discord.ui.TextInput(label="New Channel Name", max_length=100)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value
        owner_id = vc_data[str(self.vc.id)]["owner"]
        await self.vc.edit(name=new_name)
        vc_data[str(self.vc.id)]["name"] = new_name
        user_vc_names[str(owner_id)] = new_name
        save_json()

        # Rename waiting rooms if any
        for ch in self.vc.guild.voice_channels:
            if ch.name.startswith(f"{self.vc.name} waiting room"):
                await ch.edit(name=f"{new_name} waiting room")

        await interaction.response.send_message(f"Renamed channel to **{new_name}**", ephemeral=True)

class LimitModal(discord.ui.Modal, title="Set user limit"):
    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc
        self.limit_input = discord.ui.TextInput(label="User Limit (0 = unlimited)", placeholder="0", max_length=3)
        self.add_item(self.limit_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.limit_input.value)
            await self.vc.edit(user_limit=limit)
            vc_data[str(self.vc.id)]["user_limit"] = limit
            save_json()
            await interaction.response.send_message(f"Set channel limit to {limit}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid number!", ephemeral=True)

class TrustModal(discord.ui.Modal, title="Trust a user"):
    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc
        self.user_input = discord.ui.TextInput(label="User ID to trust", placeholder="123456789012345678")
        self.add_item(self.user_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_input.value)
            user = interaction.guild.get_member(user_id)
            if not user:
                return await interaction.response.send_message("User not found.", ephemeral=True)
            overwrites = self.vc.overwrites_for(user)
            overwrites.connect = True
            await self.vc.set_permissions(user, overwrite=overwrites)
            trusted = vc_data[str(self.vc.id)]["trusted_users"]
            if user.id not in trusted:
                trusted.append(user.id)
            save_json()
            await interaction.response.send_message(f"{user.mention} is now trusted.", ephemeral=True)
        except:
            await interaction.response.send_message("Invalid ID.", ephemeral=True)

class UntrustModal(discord.ui.Modal, title="Untrust a user"):
    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc
        self.user_input = discord.ui.TextInput(label="User ID to untrust", placeholder="123456789012345678")
        self.add_item(self.user_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_input.value)
            trusted = vc_data[str(self.vc.id)]["trusted_users"]
            if user_id in trusted:
                trusted.remove(user_id)
                member = interaction.guild.get_member(user_id)
                if member:
                    await self.vc.set_permissions(member, overwrite=None)
                save_json()
                await interaction.response.send_message(f"<@{user_id}> has been untrusted.", ephemeral=True)
            else:
                await interaction.response.send_message("That user is not trusted.", ephemeral=True)
        except:
            await interaction.response.send_message("Invalid ID.", ephemeral=True)

class TransferModal(discord.ui.Modal, title="Transfer ownership"):
    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc
        self.user_input = discord.ui.TextInput(label="User ID to transfer ownership to", placeholder="123456789012345678")
        self.add_item(self.user_input)
        self.view = None

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_input.value)
            user = interaction.guild.get_member(user_id)
            if not user:
                return await interaction.response.send_message("User not found.", ephemeral=True)
            vc_data[str(self.vc.id)]["owner"] = user.id
            user_vc_names[str(user.id)] = self.vc.name
            temp_channels[self.vc.id] = user.id
            save_json()
            self.view.owner_id = user.id
            await interaction.response.send_message(f"Ownership transferred to {user.mention}", ephemeral=True)
            await self.view.update_message()
        except:
            await interaction.response.send_message("Invalid ID.", ephemeral=True)

# ---------- Interface View ----------
class TempChannelView(discord.ui.View):
    def __init__(self, owner_id, vc: discord.VoiceChannel, message=None):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.vc = vc
        self.message = message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("You don’t own this channel!", ephemeral=True)
        return False

    async def update_message(self):
        data = vc_data[str(self.vc.id)]
        members = len(self.vc.members)
        locked = "🔒" if data["locked"] else "🔓"
        trusted = data["trusted_users"]
        trusted_mentions = ", ".join(f"<@{u}>" for u in trusted) if trusted else "None"
        content = f"**{data['name']}** — Owner: <@{self.owner_id}> | Members: {members} | {locked}\nTrusted users: {trusted_mentions}"

        if isinstance(self.message, discord.Message):
            try:
                await self.message.edit(content=content, view=self)
            except:
                pass
        elif isinstance(self.message, discord.TextChannel):
            try:
                await self.message.purge(limit=10)
                await self.message.send(content, view=self)
            except:
                pass

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.primary)
    async def rename_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameModal(self.vc))
        await self.update_message()

    @discord.ui.button(label="Limit", style=discord.ButtonStyle.secondary)
    async def limit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LimitModal(self.vc))
        await self.update_message()

    @discord.ui.button(label="Lock/Unlock", style=discord.ButtonStyle.danger)
    async def privacy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = vc_data[str(self.vc.id)]
        data["locked"] = not data["locked"]
        save_json()
        await interaction.response.send_message(f"Channel {'locked' if data['locked'] else 'unlocked'}.", ephemeral=True)
        await self.update_message()

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger)
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for m in self.vc.members:
            if m.id != self.owner_id:
                await m.move_to(None)
        await interaction.response.send_message("Kicked all other members!", ephemeral=True)
        await self.update_message()

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc_id = self.vc.id
        temp_channels.pop(vc_id, None)
        interface_channel = interface_channels.pop(vc_id, None)
        if interface_channel:
            try:
                await interface_channel.delete()
            except:
                pass
        vc_data.pop(str(vc_id), None)
        save_json()
        await self.vc.delete()
        await interaction.response.send_message("Channel deleted!", ephemeral=True)

    @discord.ui.button(label="Trust", style=discord.ButtonStyle.secondary)
    async def trust_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TrustModal(self.vc))
        await self.update_message()

    @discord.ui.button(label="Untrust", style=discord.ButtonStyle.secondary)
    async def untrust_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UntrustModal(self.vc))
        await self.update_message()

    @discord.ui.button(label="Transfer", style=discord.ButtonStyle.secondary)
    async def transfer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TransferModal(self.vc)
        modal.view = self
        await interaction.response.send_modal(modal)

# ---------- Voice State Update ----------
@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild

    # --- User joins lobby VC to create temp VC ---
    if after.channel and after.channel.id in LOBBY_VC_IDS:
        category = guild.get_channel(TEMP_CATEGORY_ID)
        interface_category = guild.get_channel(INTERFACE_CATEGORY_ID)
        existing_numbers = [int(ch.name.split("#")[-1])
                            for ch in category.voice_channels
                            if ch.name.startswith(TEMP_PREFIX) and ch.name.split("#")[-1].isdigit()] if category else []
        number = max(existing_numbers, default=0) + 1

        # Use last name if available
        saved_name = user_vc_names.get(str(member.id))
        temp_name = saved_name or f"{TEMP_PREFIX} #{number}"
        temp_channel = await guild.create_voice_channel(name=temp_name, category=category)

        temp_channels[temp_channel.id] = member.id
        vc_join_order[temp_channel.id] = [member.id]

        vc_data[str(temp_channel.id)] = {
            "owner": member.id,
            "trusted_users": [],
            "locked": False,
            "user_limit": 0,
            "name": temp_name
        }
        user_vc_names[str(member.id)] = temp_name
        save_json()

        await member.move_to(temp_channel)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        interface_channel = await guild.create_text_channel(
            name=f"interface-{number}",
            category=interface_category,
            overwrites=overwrites
        )
        interface_channels[temp_channel.id] = interface_channel

        view = TempChannelView(member.id, temp_channel, message=interface_channel)
        await view.update_message()

    # --- Handle joining a temp VC ---
    if after.channel and after.channel.id in temp_channels:
        vc_id = after.channel.id
        data = vc_data.get(str(vc_id), {})
        locked = data.get("locked", False)
        if locked and member.id != data.get("owner") and member.id not in data.get("trusted_users", []):
            waiting_name = f"{data['name']} waiting room"
            category = after.channel.category
            waiting_room = await guild.create_voice_channel(name=waiting_name, category=category)
            await member.move_to(waiting_room)
            async def delete_waiting():
                await asyncio.sleep(60)
                if len(waiting_room.members) == 0:
                    await waiting_room.delete()
            asyncio.create_task(delete_waiting())
            return

        if vc_id not in vc_join_order:
            vc_join_order[vc_id] = []
        if member.id not in vc_join_order[vc_id]:
            vc_join_order[vc_id].append(member.id)

    # --- Handle leaving temp VC ---
    if before.channel and before.channel.id in temp_channels:
        vc_id = before.channel.id
        owner_id = temp_channels.get(vc_id)

        if vc_id in vc_join_order and member.id in vc_join_order[vc_id]:
            vc_join_order[vc_id].remove(member.id)

        async def delete_if_empty_or_transfer():
            await asyncio.sleep(AUTO_DELETE_DELAY)
            ch = before.channel
            if ch:
                if len(ch.members) == 0:
                    temp_channels.pop(vc_id, None)
                    vc_join_order.pop(vc_id, None)
                    vc_data.pop(str(vc_id), None)
                    save_json()
                    interface_channel = interface_channels.pop(vc_id, None)
                    if interface_channel:
                        try:
                            await interface_channel.delete()
                        except:
                            pass
                    await ch.delete()
                elif owner_id == member.id and len(ch.members) > 0:
                    new_owner_id = vc_join_order[vc_id][0]
                    temp_channels[vc_id] = new_owner_id
                    vc_data[str(vc_id)]["owner"] = new_owner_id
                    user_vc_names[str(new_owner_id)] = vc_data[str(vc_id)]["name"]
                    save_json()
                    interface_channel = interface_channels.get(vc_id)
                    if interface_channel:
                        view = TempChannelView(new_owner_id, ch, message=interface_channel)
                        await view.update_message()
        asyncio.create_task(delete_if_empty_or_transfer())

# ---------- On Ready ----------
@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}!")
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("Guild not found!")
        return

    # Restore temp channels
    for vc_id_str, data in vc_data.items():
        vc_id = int(vc_id_str)
        channel = guild.get_channel(vc_id)
        if channel:
            temp_channels[vc_id] = data["owner"]
            interface_channel = interface_channels.get(vc_id)
            if not interface_channel:
                interface_category = guild.get_channel(INTERFACE_CATEGORY_ID)
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.get_member(data["owner"]): discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
                interface_channel = await guild.create_text_channel(
                    name=f"interface-{channel.name}",
                    category=interface_category,
                    overwrites=overwrites
                )
                interface_channels[vc_id] = interface_channel
            view = TempChannelView(data["owner"], channel, message=interface_channel)
            await view.update_message()

bot.run("YOUR_BOT_TOKEN_HERE")
