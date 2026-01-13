import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio
import random
import re
import time

load_dotenv()

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!!?", intents=intents)

private_channels = {}
channel_locks = {}

DEFAULT_GREETINGS = [
    "{member.mention} VCチャットはこっちだよ！",
    "{member.mention} まあ、ご来訪いただき恐悦至極でございます。どうぞお入りくださいませ",
    "{member.mention} ご来訪を心よりお待ち申し上げておりました。どうぞお入りいただき、おくつろぎください。",
    "{member.mention} お客様のご来訪、誠に光栄でございます。どうぞお気軽にお入りくださいませ。",
    "{member.mention} あんた、ここに来るなんて…まあ、入ってもいいけどね！",
    "{member.mention} なんであんたが来たのか分からないけど、仕方ないわね。入っていいわよ。",
    "{member.mention} 何でこんなところに？別に歓迎してるわけじゃないんだから。まあ、入っていいわよ。",
    "{member.mention} あら、ここに来たのね。どうぞ、どうぞ、お入りなさい。",
    "{member.mention} わあ、来てくれたんだね。どうぞ、お気軽にお入りください。",
    "{member.mention} 闇の扉を叩いた者よ、我が領域への侵入を許可する。",
    "{member.mention} おお、来たるべき者が現れたか。さあ、我が深淵へ進め！",
    "{member.mention} 運命の導きにより、ここへ辿り着いたか。恐れることなく、入っておくれ。",
    "{member.mention} 終焉の地にてお前を待ち受けていた。勇気を持ち、我が領域へ入るがいい。",
    "{member.mention} ご来訪誠にありがとうございます。どうぞお入りくださいませ、お客様。",
    "{member.mention} いらっしゃいませ、お客様。こちらへどうぞお進みいただき、おくつろぎいただければと存じます。",
    "{member.mention} ご来館いただき、誠にありがとうございます。どうぞお気軽にお入りください。",
    "{member.mention} お越しいただき光栄でございます。どうぞお入りいただき、おくつろぎください。",
]


def sanitize_channel_name(name):
    name = name.strip()
    name = name.replace(" ", "-")
    name = re.sub(r'[^a-zA-Z0-9\-_]', '', name)
    name = re.sub(r'-+', '-', name)
    name = name.strip('-')
    name = name[:100]
    if not name:
        name = f"vc-{int(time.time())}"
    return name.lower()


async def send_greeting(member, text_channel):
    if member.bot:
        return
    
    try:
        greeting_template = random.choice(DEFAULT_GREETINGS)
        greeting_message = greeting_template.format(member=member)
        await text_channel.send(greeting_message)
    except discord.Forbidden:
        print(f"権限不足: {text_channel.name}にメッセージを送信できません")
    except discord.HTTPException as e:
        print(f"メッセージ送信エラー: {e}")


async def create_private_text_channel(guild, voice_channel, member):
    sanitized_name = sanitize_channel_name(voice_channel.name)
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    
    try:
        private_channel = await guild.create_text_channel(
            name=sanitized_name,
            overwrites=overwrites,
            category=voice_channel.category,
            reason=f"VC連動プライベートチャンネル: {voice_channel.name}"
        )
        print(f"テキストチャンネル作成: {private_channel.name} (VC: {voice_channel.name})")
        return private_channel
    except discord.Forbidden:
        print(f"権限不足: テキストチャンネルを作成できません")
        return None
    except discord.HTTPException as e:
        print(f"チャンネル作成エラー: {e}")
        return None


@bot.event
async def on_ready():
    print(f"{bot.user} がオンラインになりました")
    print(f"{len(bot.guilds)}個のサーバーに接続中")
    print("ステートレスモード: チャンネルマッピングはメモリキャッシュのみ")
    
    to_remove = []
    for voice_channel_id, text_channel_id in list(private_channels.items()):
        voice_channel = bot.get_channel(int(voice_channel_id))
        text_channel = bot.get_channel(int(text_channel_id))
        
        if not voice_channel or not text_channel:
            to_remove.append(voice_channel_id)
            print(f"無効なマッピングを削除: VC={voice_channel_id}, TC={text_channel_id}")
    
    for vc_id in to_remove:
        private_channels.pop(vc_id)
    
    if to_remove:
        print(f"{len(to_remove)}件の無効なエントリを削除しました")
    
    print("起動完了")


@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and (before.channel != after.channel):
        await handle_user_join(member, after.channel)
    
    if before.channel and (before.channel != after.channel):
        await handle_user_leave(member, before.channel)


async def handle_user_join(member, voice_channel):
    guild = voice_channel.guild
    voice_channel_id = str(voice_channel.id)
    
    if voice_channel_id not in channel_locks:
        channel_locks[voice_channel_id] = asyncio.Lock()
    
    async with channel_locks[voice_channel_id]:
        text_channel = None
        
        if voice_channel_id in private_channels:
            text_channel_id = private_channels[voice_channel_id]
            text_channel = guild.get_channel(int(text_channel_id))
            
            if not text_channel:
                print(f"マッピングされたテキストチャンネルが存在しません: {text_channel_id}")
                private_channels.pop(voice_channel_id)
                text_channel = None
        
        if text_channel is None:
            sanitized_name = sanitize_channel_name(voice_channel.name)
            
            await guild.fetch_channels()
            
            text_channel = discord.utils.get(
                guild.text_channels,
                name=sanitized_name,
                category=voice_channel.category
            )
            
            if text_channel is None:
                await asyncio.sleep(0.3)
                await guild.fetch_channels()
                
                text_channel = discord.utils.get(
                    guild.text_channels,
                    name=sanitized_name,
                    category=voice_channel.category
                )
                
                if text_channel is None:
                    text_channel = await create_private_text_channel(guild, voice_channel, member)
                    
                    if text_channel is None:
                        print(f"テキストチャンネルの作成に失敗: {voice_channel.name}")
                        return
            
            private_channels[voice_channel_id] = str(text_channel.id)
        
        try:
            await text_channel.set_permissions(
                member,
                read_messages=True,
                send_messages=True,
                reason=f"{member.name}がボイスチャンネルに参加"
            )
            print(f"権限付与: {member.name} → {text_channel.name}")
        except discord.Forbidden:
            print(f"権限不足: {member.name}に権限を付与できません")
        except discord.HTTPException as e:
            print(f"権限設定エラー: {e}")
        
        await send_greeting(member, text_channel)


async def handle_user_leave(member, voice_channel):
    guild = voice_channel.guild
    voice_channel_id = str(voice_channel.id)
    
    if voice_channel_id not in private_channels:
        return
    
    text_channel_id = private_channels[voice_channel_id]
    text_channel = guild.get_channel(int(text_channel_id))
    
    if not text_channel:
        private_channels.pop(voice_channel_id)
        print(f"メモリキャッシュから削除: VC={voice_channel_id}")
        return
    
    if not member.bot:
        try:
            await text_channel.set_permissions(
                member,
                overwrite=None,
                reason=f"{member.name}がボイスチャンネルから退出"
            )
            print(f"権限削除: {member.name} ← {text_channel.name}")
        except discord.Forbidden:
            print(f"権限不足: {member.name}の権限を削除できません")
        except discord.HTTPException as e:
            print(f"権限削除エラー: {e}")
    
    if len(voice_channel.members) == 0:
        try:
            deleted_count = await text_channel.purge(limit=None)
            print(f"メッセージ削除: {text_channel.name} ({len(deleted_count)}件)")
        except discord.Forbidden:
            print(f"権限不足: {text_channel.name}のメッセージを削除できません")
        except discord.HTTPException as e:
            print(f"メッセージ削除エラー: {e}")


if __name__ == '__main__':
    token = os.getenv('BOT_TOKEN')
    if not token:
        print("エラー: BOT_TOKENが設定されていません")
        exit(1)
    
    bot.run(token)
