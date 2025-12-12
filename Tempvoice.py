import discord
from discord.ext import commands
import asyncio

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
# ==================

temp_channels = {}
channel_owners = {}
interface_channels = {}
trusted_users = {}
vc_join_order = {}

# ---------- Modals ----------
class RenameModal(discord.ui.Modal, title="Rename your temp channel"):
    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc
        self.name_input = discord.ui.TextInput(label="New Channel Name", max_length=100)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.vc.edit(name=self.name_input.value)
        await interaction.response.send_message(f"Renamed channel to **{self.name_input.value}**", ephemeral=True)

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
            trusted_users.setdefault(self.vc.id, [])
            if user.id not in trusted_users[self.vc.id]:
                trusted_users[self.vc.id].append(user.id)
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
            if self.vc.id in trusted_users and user_id in trusted_users[self.vc.id]:
                trusted_users[self.vc.id].remove(user_id)
                user = interaction.guild.get_member(user_id)
                if user:
                    await self.vc.set_permissions(user, overwrite=None)
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

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_input.value)
            user = interaction.guild.get_member(user_id)
            if not user:
                return await interaction.response.send_message("User not found.", ephemeral=True)
            temp_channels[self.vc.id] = user.id
            channel_owners[user.id] = self.vc.id
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
        members = len(self.vc.members)
        locked = "🔒" if self.vc.overwrites_for(self.vc.guild.default_role).connect is False else "🔓"
        trusted = trusted_users.get(self.vc.id, [])
        trusted_mentions = ", ".join(f"<@{u}>" for u in trusted) if trusted else "None"
        content = (
            f"**{self.vc.name}** — Owner: <@{self.owner_id}> | Members: {members} | {locked}\n"
            f"Trusted users: {trusted_mentions}"
        )

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
        guild = self.vc.guild
        overwrites = self.vc.overwrites_for(guild.default_role)
        if overwrites.connect is False:
            await self.vc.set_permissions(guild.default_role, connect=True)
        else:
            await self.vc.set_permissions(guild.default_role, connect=False)
        await interaction.response.send_message("Privacy toggled.", ephemeral=True)
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
        owner_id = temp_channels.pop(self.vc.id, None)
        if owner_id:
            channel_owners.pop(owner_id, None)
            trusted_users.pop(self.vc.id, None)
            vc_join_order.pop(self.vc.id, None)
            interface_channel = interface_channels.pop(self.vc.id, None)
            if interface_channel:
                try:
                    await interface_channel.delete()
                except:
                    pass
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
    if after.channel and after.channel.id in LOBBY_VC_IDS:
        guild = member.guild
        category = guild.get_channel(TEMP_CATEGORY_ID) if TEMP_CATEGORY_ID else None
        interface_category = guild.get_channel(INTERFACE_CATEGORY_ID)

        existing_numbers = [int(ch.name.split("#")[-1])
                            for ch in category.voice_channels if ch.name.startswith(TEMP_PREFIX) and ch.name.split("#")[-1].isdigit()] \
            if category else []

        number = max(existing_numbers, default=0) + 1
        temp_name = f"{TEMP_PREFIX} #{number}"

        temp_channel = await guild.create_voice_channel(name=temp_name, category=category)

        temp_channels[temp_channel.id] = member.id
        channel_owners[member.id] = temp_channel.id
        vc_join_order[temp_channel.id] = [member.id]
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

    if after.channel and after.channel.id in temp_channels:
        if after.channel.id not in vc_join_order:
            vc_join_order[after.channel.id] = []
        if member.id not in vc_join_order[after.channel.id]:
            vc_join_order[after.channel.id].append(member.id)

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
                    owner_id = temp_channels.pop(vc_id, None)
                    if owner_id:
                        channel_owners.pop(owner_id, None)
                        trusted_users.pop(vc_id, None)
                        vc_join_order.pop(vc_id, None)
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
                    channel_owners[new_owner_id] = vc_id
                    interface_channel = interface_channels.get(vc_id)
                    if interface_channel:
                        view = TempChannelView(new_owner_id, ch, message=interface_channel)
                        await view.update_message()

        asyncio.create_task(delete_if_empty_or_transfer())

# ---------- On Ready ----------
@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}!")

bot.run("YOUR_BOT_TOKEN_HERE")
