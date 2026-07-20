import os
import io
import re
import string
import random
import requests
import discord
import aiohttp
import time
from discord.ext import commands
from datetime import datetime
from threading import Thread
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "Bot is online!"

def run():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run)
    t.start()

TOKEN = os.getenv("DISCORD_TOKEN", "DISCORD_TOKEN")
PRETTY_MODE = True

def optimize_obfuscation_patterns(lua_code):
    lua_code = re.sub(r'local\s+\w+,\s*env;\s*local\s+env\s*=\s*env;', 'local v1, env;\nlocal env = env;', lua_code)
    lua_code = re.sub(r'local\s+\w+\s*=\s*\{\s*game:[hH]ttp[gG]et.*?\};', '', lua_code)
    lua_code = re.sub(r'for\s+i\s*=\s*1,\s*256,\s*1\s+do\s*\w+\[i\]\s*=\s*i;\s*end;?', '', lua_code)
    lua_code = re.sub(r'repeat\s+\w+\s*=\s*\w+\(1,\s*#\w+\);\s*\w+\s*=\s*\w+\(\w+,\s*\w+\);\s*until\s*#\w+\s*==\s*0;?', '', lua_code)
    lua_code = re.sub(r'\w+\s*=\s*\(?\w+\s*\*\s*\d+\s*\+\s*\d+\)?\s*%\s*\d+;?', '', lua_code)
    lua_code = re.sub(r'repeat\s*until\s*false;?', '', lua_code)
    lua_code = re.sub(r'if\s+#\d+\s*==\s*0\s+then\s*end;?', '', lua_code)
    lua_code = re.sub(r'if\s*\w+\[\w+\]\s+then\s*else\s*', 'if not v20[arg2] then ', lua_code)
    lua_code = re.sub(r'\w+\(\s*\(?\(?\w+\s*%\s*\d+\)?\s*/\s*2\s*\^\s*\(?[^)]+\)?\)?\s*\);?', '', lua_code)
    lua_code = re.sub(r'\w+\(\s*\(?\(?\(?\(?\w+\s*%\s*\d+\)?\s*/\s*2\s*\^\s*\(?[^)]+\)?\)?\s*%\s*\d+\)?\s*/\s*2\s*\^\s*\(?[^)]+\)?\)?\s*%\s*\d+\)?\s*\*\s*\d+\s*\);?', '', lua_code)
    
    lines = lua_code.splitlines()
    cleaned_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "for i = 1, LocalPlayer.len(arg1)" in stripped or "v4[arg2] .. v3[" in stripped:
            continue
        if "math.floor" in stripped and ("table.remove" in stripped or i + 3 < len(lines) and "table.remove" in lines[i+1] or "table.remove" in lines[i+2]):
            continue
        if "setmetatable" in stripped and "__index" in stripped and "__metatable = nil" in stripped:
            continue
        if stripped in ["v8 = {};", "v14 = {};", "v22 = {};", "var_8 = {};", "var_14 = {};", "var_22 = {};"]:
            continue
        if stripped.startswith("v20 = v") or stripped.startswith("v11 = v") or stripped.startswith("var_20 = var_") or stripped.startswith("var_11 = var_"):
            continue
        if "local items =" in stripped and "__index" in stripped:
            continue
        if "local v23 = setmetatable" in stripped or "local v2 = v23" in stripped or "local var_23 = setmetatable" in stripped:
            continue
        if "string.byte(arg1, i)" in stripped or "string.len(arg1)" in stripped or "lookup_2" in stripped:
            continue
        if stripped == "end;" and i > 0 and ("string.byte" in lines[i-1] or "v4[arg2]" in lines[i-1] or "var_4[arg2]" in lines[i-1]):
            continue
        cleaned_lines.append(line)
        
    lua_code = "\n".join(cleaned_lines)
    return lua_code

def compress_loadstring_patterns(lua_code):
    url_pattern = r'(\w+)\s*=\s*\{\s*game:[hH]ttp[gG]et\(\s*["\'](https?://[^\s"\']+)["\']\s*\)\s*\}\s*;?'
    urls_found = re.findall(url_pattern, lua_code)
    
    for vname, url in urls_found:
        loadstring_pattern = r'(\w+)\s*=\s*loadstring\(\s*\w+\(\s*' + vname + r'\s*\)\s*\)\s*\;?'
        if re.search(loadstring_pattern, lua_code):
            replacement_code = f'local Loader = loadstring(game:HttpGet("{url}"))'
            lua_code = re.sub(loadstring_pattern, replacement_code, lua_code)
            lua_code = re.sub(r'\b' + vname + r'\s*=\s*\{\s*game:[hH]ttp[gG]et\(\s*["\']' + re.escape(url) + r'["\']\s*\)\s*\;?', '', lua_code)
    return lua_code

def heuristic_metatable_decoder(lua_code):
    lookup_pattern = r'\(\s*["\'](.*?)(?:\\.|[^"\'])*["\']\s*\)\[\s*\d{5,}\s*\]'
    lua_code = re.sub(lookup_pattern, 'nil', lua_code)
    dynamic_pattern = r'\(\s*(["\'](?:\\.|[^"\'])*["\'])\s*\)\[\s*[^\]]+\s*\]'
    lua_code = re.sub(dynamic_pattern, r'\1', lua_code)
    lua_code = re.sub(r'\.CFrame\s*\*\s*[0-9]{10,}', '.CFrame', lua_code)
    bad_index_pattern = r'\w+\[\s*(?:"[^"]*"|\'[^\']*\'|\d{6,})\s*\]'
    lua_code = re.sub(bad_index_pattern, 'nil', lua_code)
    junk_str_assign = r'\blocal\s+\w+\s*=\s*["\'][\x00-\x1F\x7F-\x9F].*?["\'];?'
    lua_code = re.sub(junk_str_assign, "", lua_code)
    return lua_code

def sanitize_junk_expressions(lua_code):
    lines = lua_code.splitlines()
    for i, line in enumerate(lines):
        if ".Connect(" in line:
            lines[i] = re.sub(r'([\w_]+)\.([\w_]+)\.Connect\(\s*[\w_.]+\s*,\s*([\w_]+)\s*\)', r'\1.\2:Connect(\3)', line)
        
    lua_code = "\n".join(lines)
    junk_patterns = [
        r'\([0-9]{10,}\)\s*\([^)]*\);?',
        r'\b\w+\s*=\s*\(?[0-9]{10,}\)?\s*;?',
        r'\b\w+\s*\(\s*[0-9]{10,}\s*,\s*[0-9]{10,}\s*\);?',
        r'\b\w+\[\d+\]\s*=\s*\w+\[\w+\[\d+\]\];?',
        r'if\s+not\s+pcall\(.*?\)\s+then\s*end;?',
        r'\(\s*["\'](?:[^"\\]|\\.)*["\']\s*\)\s*\(\s*["\'](?:[^"\\]|\\.)*["\']\s*,\s*[0-9]{10,}\s*\);?',
        r'\b\w+\s*\(\s*["\'](?:[^"\\]|\\.)*["\']\s*,\s*["\'](?:[^"\\]|\\.)*["\']\s*\);?'
    ]
    for pattern in junk_patterns:
        lua_code = re.sub(pattern, "", lua_code)

    cleaned_lines = []
    for line in lua_code.splitlines():
        stripped = line.strip()
        if not stripped or stripped == ";" or stripped.endswith("="):
            continue
        if "== " in line and " then " in line and not stripped.startswith("if"):
            line = re.sub(r'^(\s*)', r'\1 if ', line)
            if not line.endswith("end") and "local" in line:
                line = line + " end"
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def decode_lua_decimal_escapes(lua_code):
    pattern = r'((?:\\[0-9]{1,3})+)'
    def replace_escape(match):
        raw_escapes = match.group(1)
        numbers = [int(n) for n in raw_escapes.split('\\') if n]
        try:
            return bytes(numbers).decode('utf-8', errors='ignore')
        except Exception:
            return raw_escapes
    return re.sub(pattern, replace_escape, lua_code)

def normalize_variables(lua_code):
    obfuscated_patterns = [
        r'\bvar_\d+\b', r'\b[a-zA-Z_]\w*_ref\d*\b', r'\b[a-zA-Z_]\w*_fn\b',
        r'\br\d+\b', r'\bn\d+\b', r'\bv\d+\b'
    ]
    found_vars = []
    for pattern in obfuscated_patterns:
        for match in re.findall(pattern, lua_code):
            if match not in found_vars and match not in [
                "game", "workspace", "pairs", "unpack", "table", "wait", "env",
                "Color3", "string", "loadstring", "pcall", "true", "false", "debug", "tostring", "math"
            ]:
                found_vars.append(match)

    placeholder_map = {}
    for idx, old_var in enumerate(found_vars, start=1):
        placeholder = f"___TEMP_vXYZ_{idx}___"
        placeholder_map[placeholder] = f"v{idx}"
        lines = lua_code.splitlines()
        for i, line in enumerate(lines):
            if "WEBHOOK" in line:
                continue
            lines[i] = re.sub(r'\b' + re.escape(old_var) + r'\b', placeholder, line)
        lua_code = "\n".join(lines)
        
    for placeholder, clean_name in placeholder_map.items():
        lua_code = lua_code.replace(placeholder, clean_name)

    lines = lua_code.splitlines()
    active_var_maps = {}
    module_counter = 0
    instance_counters = {}
    
    for i, line in enumerate(lines):
        if "WEBHOOK" in line:
            continue
        for generic_var, actual_name in list(active_var_maps.items()):
            line = re.sub(r'\b' + re.escape(generic_var) + r'\b', actual_name, line)

        service_match = re.search(r'(?:local\s+)?(\bv\d+\b)\s*=\s*(?:game|cloneref\s*\(\s*game\s*\)|[a-zA-Z0-9_]*)[.:][gG]etService\s*\(\s*(?:game\s*,\s*)?["\'](\w+)["\']\s*\)', line)
        if service_match:
            v_name, s_name = service_match.group(1), service_match.group(2)
            active_var_maps[v_name] = s_name
            line = f'local {s_name} = game:GetService("{s_name}")'

        req_match = re.search(r'(?:local\s+)?(\bv\d+\b)\s*=\s*require\s*\s*\(', line)
        if req_match:
            v_name = req_match.group(1)
            module_counter += 1
            active_var_maps[v_name] = f"ModuleData_{module_counter}"
            line = re.sub(r'\b' + re.escape(v_name) + r'\b', f"ModuleData_{module_counter}", line)

        lp_match = re.search(r'(?:local\s+)?(\bv\d+\b)\s*=\s*(?:game\.Players|Players|[a-zA-Z0-9_]+)\.LocalPlayer\b', line)
        if lp_match:
            v_name = lp_match.group(1)
            active_var_maps[v_name] = "LocalPlayer"
            line = f'local LocalPlayer = game.Players.LocalPlayer'

        char_match = re.search(r'(?:local\s+)?(\bv\d+\b)\s*=\s*LocalPlayer\.Character\b', line)
        if char_match:
            v_name = char_match.group(1)
            active_var_maps[v_name] = "Character"
            line = re.sub(r'\b' + re.escape(v_name) + r'\b', "Character", line)

        hrp_match = re.search(r'(?:local\s+)?(\bv\d+\b)\s*=\s*(?:Character|[a-zA-Z0-9_]+)\.HumanoidRootPart\b', line)
        if hrp_match:
            v_name = hrp_match.group(1)
            active_var_maps[v_name] = "HumanoidRootPart"
            line = re.sub(r'\b' + re.escape(v_name) + r'\b', "HumanoidRootPart", line)

        inst_match = re.search(r'(?:local\s+)?(\bv\d+\b)\s*=\s*Instance\.new\s*\(\s*["\'](\w+)["\']', line)
        if inst_match:
            v_name, class_name = inst_match.group(1), inst_match.group(2)
            if class_name not in instance_counters:
                instance_counters[class_name] = 1
            else:
                instance_counters[class_name] += 1
            clean_name = f"{class_name}_{instance_counters[class_name]}"
            active_var_maps[v_name] = clean_name
            line = re.sub(r'\b' + re.escape(v_name) + r'\b', clean_name, line)

        if line.strip() == ".Players.LocalPlayer.Character;" or re.match(r'^\s*\.Players\.\w+\.Character\s*;?$', line):
            line = ""
        line = re.sub(r'\.Players\.\bv\d+\b', '.Players.LocalPlayer', line)
        if "character." in line: line = line.replace("character.", "Character.")
        if "character:" in line: line = line.replace("character:", "Character:")
        if "humanoidRootPart." in line: line = line.replace("humanoidRootPart.", "HumanoidRootPart.")
        if "humanoid." in line: line = line.replace("humanoid.", "Humanoid.")
        lines[i] = line

    lua_code = "\n".join(lines)
    cleaned_lines = []
    for line in lua_code.splitlines():
        if not line.strip():
            continue
        if re.match(r'^\s*ModuleData_\d+\s*=\s*ModuleData_\d+\s*;?$', line) or re.match(r'^\s*LocalPlayer\s*=\s*LocalPlayer\s*;?$', line):
            continue
        if re.search(r'\bPlayerGui\s*=\s*UDim2\.new', line):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def unflatten_control_flow(lua_code):
    block_pattern = re.compile(r'(?:if|elseif)\s+\w+\s*==\s*([0-9\x22\x27\w]+)\s+then\s*(.*?)(?=\s*(?:elseif|else|end\s*$))', re.DOTALL)
    state_mutation_pattern = re.compile(r'\w+\s*=\s*([0-9\x22\x27\w]+)\s*$')
    blocks = block_pattern.findall(lua_code)
    if not blocks:
        return lua_code
        
    block_map = {}
    start_state = None
    state_init = re.search(r'local\s+\w+\s*=\s*([0-9\x22\x27\w]+)', lua_code)
    if state_init:
        start_state = state_init.group(1)

    for state_val, block_content in blocks:
        block_content_stripped = block_content.strip()
        lines = block_content_stripped.splitlines()
        next_state = None
        if lines:
            last_line = lines[-1].strip()
            mutation_match = state_mutation_pattern.search(last_line)
            if mutation_match:
                next_state = mutation_match.group(1)
                block_content_stripped = "\n".join(lines[:-1]).strip()
        block_map[state_val] = {"content": block_content_stripped, "next": next_state}
        if not start_state:
            start_state = state_val

    reconstructed_lines = []
    current_state = start_state
    visited_states = set()

    while current_state in block_map and current_state not in visited_states:
        visited_states.add(current_state)
        node = block_map[current_state]
        if node["content"]:
            reconstructed_lines.append(node["content"])
        current_state = node["next"]
    if reconstructed_lines:
        return "\n".join(reconstructed_lines)
    return lua_code

def beautify_lua(content):
    try:
        response = requests.post(
            "https://relua.lua.cz/deobfuscate",
            json={"filename": "script.lua", "source": content, "lua_version": "Lua51", "pretty": PRETTY_MODE},
            timeout=50
        )
        response.raise_for_status()
        result = response.json()

        if "output" in result:
            output = unflatten_control_flow(result["output"])
            lines = output.splitlines()
            if len(lines) > 0:
                top_limit = min(65, len(lines))
                top_part = "\n".join(lines[:top_limit])
                bottom_part = "\n".join(lines[top_limit:])
                
                top_part = re.sub(r'^.for\s+i\s*=\s*1\s*,\s*\w+\.len\(arg1\)\s*,\s*1\s+do.*?end\s*;?', '', top_part, flags=re.DOTALL | re.MULTILINE).strip()
                top_part = re.sub(r'(?:local\s+\w+\s*=\s*[^;]+;?\s*)*local\s+lookup\s*=\s*\{\};.*?\brepeat\b.*?\buntil\s+#lookup\s*==\s*0;?', '', top_part, flags=re.DOTALL).strip()
                top_part = re.sub(r'local\s+\w+\s*=\s*function\(arg1,\s*arg2,.*?\).*?\breturn\s+table\.remove\(.*?\);\s*end;?', '', top_part, flags=re.DOTALL).strip()
                top_part = re.sub(r'\w+\s*=\s*function\(arg1,\s*arg2,.*?\).*?for\s+i\s*=\s*1,\s*\w+\.len\(arg1\).*?\bend;\s*.*?return\s+\w+;\s*end;?', '', top_part, flags=re.DOTALL).strip()
                top_part = re.sub(r'local\s+\w+\s*=\s*\w+;?', '', top_part).strip()
                top_part = re.sub(r'\w+\s*=\s*\{\s*\};?', '', top_part).strip()
                top_part = re.sub(r'setmetatable\(\s*\{\}\s*,\s*\w+\s*\);?', '', top_part).strip()
                top_part = re.sub(r'^end\s*;?', '', top_part, flags=re.MULTILINE).strip()

                output = f"{top_part}\n{bottom_part}" if bottom_part else top_part

            output = heuristic_metatable_decoder(output)
            output = sanitize_junk_expressions(output)
            output = normalize_variables(output)
            output = compress_loadstring_patterns(output)
            output = optimize_obfuscation_patterns(output)
            final_clean = decode_lua_decimal_escapes(output)
                
            return re.sub(r'\n\s*\n\s*\n+', '\n\n', final_clean).strip()
        return None
    except Exception as e:
        print(f"API Error: {e}")
        return None

def fetch_url(url):
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Failed to fetch URL: {e}")
        return None

def generate_random_filename():
    return ''.join(random.choice(string.ascii_letters) for _ in range(10)) + ".lua"

def extract_link(text):
    url_match = re.search(r'(https?://[^\s]+)', text)
    return url_match.group(1) if url_match else None

def string_to_discordfile(content_str, filename="dumpie_get.lua"):
    return discord.File(fp=io.BytesIO(content_str.encode('utf-8')), filename=filename)

async def asyncget(url, headers=None, proxy=None, proxy_auth=None):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, proxy=proxy, proxy_auth=proxy_auth, timeout=15) as response:
            return await response.text()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents, activity=discord.Game(name="Send links/files to deobf"), help_command=None)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")

async def process_promdeobf(message, content_source):
    status_msg = await message.reply("Processing deobfuscation... The results will be sent to your DMs!")
    start_time = time.time()
    output = beautify_lua(content_source)

    if not output:
        await status_msg.edit(content=f"{message.author.mention} Failed to deobfuscate code via the API.")
        return

    end_time = time.time()
    processed_time = int((end_time - start_time) * 1000)
    finished_time = int((end_time - start_time) * 1000) + random.randint(1500, 3500)
    
    banner = (
        "      _        _____  _    _ __  __ _____  ______ _____  \n"
        "     | |      |  __ \\| |  | |  \\/  |  __ \\|  ____|  __ \\ \n"
        "  ___| | _____| |  | | |  | | \\  / | |__) | |__  | |__) |\n"
        " / __| |/ / __| |  | | |  | | |\\/| |  ___/|  __| |  _  / \n"
        " \\__ \\   <\\__ \\ |__| | |__| | |  | | |    | |____| | \\ \\ \n"
        " |___/_|\\_\\___/_____/ \\____/|_|  |_|_|    |______|_|  \\_\\\n"
        " Join Discord To Dump Scripts : https://discord.gg/Xcusy2qp\n"
    )
    final_output = f"--[[\n{banner}\n]]\n\n{output}"

    embed = discord.Embed(
        title="Here's Your Script!",
        description=f"Processed script in {processed_time}ms; finished everything in {finished_time}ms.\nSuccessfully processed.",
        color=discord.Color.from_rgb(255, 165, 0)
    )

    try:
        await status_msg.edit(content=f"{message.author.mention} Done! Check your DMs for the output.")
        
        await message.author.send(embed=embed)
        
        if len(final_output) <= 1900:
            await message.author.send(content=f"```lua\n{final_output}\n```")
        else:
            filename = generate_random_filename()
            file_data = string_to_discordfile(final_output, filename=filename)
            await message.author.send(file=file_data)
    except Exception:
        await status_msg.edit(content=f"{message.author.mention} Done! However, I couldn't open a DM link with you. Check your privacy setup.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if message.channel.id != 1511662026055749713:
        return

    if message.attachments:
        attachment = message.attachments[0]
        if attachment.filename.endswith(('.lua', '.txt')):
            try:
                content_bytes = await attachment.read()
                content = content_bytes.decode("utf-8", errors="ignore")
                if content.strip():
                    await process_promdeobf(message, content)
                    return
            except Exception as e:
                print(f"Failed to read attached file: {e}")

    extracted_url = extract_link(message.content)
    if extracted_url:
        content = fetch_url(extracted_url)
        if content and content.strip():
            await process_promdeobf(message, content)
            return

    await bot.process_commands(message)

keep_alive()
bot.run(TOKEN)
