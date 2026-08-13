

const TOKEN = process.env.TOKEN;

const { Client, GatewayIntentBits, ActivityType, AttachmentBuilder, EmbedBuilder } = require('discord.js');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const zlib = require('zlib'); // Built-in Node zlib module
const luamin = require('lua-format');
const beautify = require('./modules/lua_beautifier.js');
const deobfLuaobf = require('./modules/lua_deobf.js');

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.DirectMessages
    ]
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('Unhandled Rejection at:', promise, 'reason:', reason);
});

process.on('uncaughtException', (err) => {
    console.error('Uncaught Exception:', err);
});

process.on('uncaughtExceptionMonitor', (err, origin) => {
    console.error('Uncaught Exception Monitor:', err, origin);
});

const webhookRegex = /https?:\/\/(?:ptb\.|canary\.)?discord(?:app)?\.com\/api\/webhooks\/\d+\/[a-zA-Z0-9_-]+/g;
const splicedRegex = /['"]\/api\/webhooks\/\d+\/[a-zA-Z0-9_-]+['"]/g;
const urlRegex = /https?:\/\/[^\s"'<>]+/g;

const PREFIX = '.l';
const UPLOAD_PREFIX = '.upload';
const LUAMIN_PREFIX = '.beautify';
const ALLOWED_CHANNEL = '1517760356364189836';

const STATS_FILE = path.join(__dirname, 'command_stats.json');

function getCommandStats() {
    try {
        if (fs.existsSync(STATS_FILE)) {
            return JSON.parse(fs.readFileSync(STATS_FILE, 'utf8'));
        }
    } catch (e) {
        console.error("Failed to read command stats:", e);
    }
    return {};
}

function incrementCommandCount(userId) {
    try {
        const stats = getCommandStats();
        stats[userId] = (stats[userId] || 0) + 1;
        fs.writeFileSync(STATS_FILE, JSON.stringify(stats, null, 2), 'utf8');
    } catch (e) {
        console.error("Failed to save command stats:", e);
    }
}

async function uploadToPastefy(content) {
    try {
        const response = await fetch("https://pastefy.app/api/v2/paste", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                content: content,
                title: "Upload",
                encrypted: false,
                visibility: "UNLISTED",
                type: "PASTE",
                tags: [],
                ai: true
            })
        });
        const data = await response.json();
        return data.success && data.paste?.raw_url ? data.paste.raw_url : null;
    } catch (e) {
        console.error("Pastefy failed:", e);
        return null;
    }
}

client.once('ready', () => {
    console.log(`Logged in as ${client.user.tag}`);
    client.user.setActivity('.help - bot', { type: ActivityType.Watching });
});

client.on('messageCreate', async (message) => {
    if (message.author.bot) return;

    if (message.content === '.help') {
        incrementCommandCount(message.author.id);
        const helpEmbed = new EmbedBuilder()
            .setTitle('Commands List')
            .setColor('Blurple')
            .setDescription(`
                \`[ .l ]\` > Env Logged obfuscated Lua code.
                \`[ .v2 ]\` > Run v2 env logger script.
                \`[ .promdeobf ]\` > Deobfuscated Prometheus / WeAreDevs obfuscated Lua code.
                \`[ .compress ]\` > Compress Lua code into a fast-loading payload.
                \`[ .upload ]\` > Upload file/link/codeblock to Pastefy.
                \`[ .get ]\` > Sends a GET request to a website and returns the data.
                \`[ .webhook ]\` > Capturing Webhooks from Scripts.
                \`[ .beautify ]\` > Beautify Lua code (file/link/codeblock).
                \`[ .minify ]\` > Minify Lua code (remove whitespace/comments).
                \`[ .leaderboard ]\` > View the top 10 command users.
                \`[ .rank ]\` > Check your position on the leaderboard.
                \`[ .help ]\` > Shows this help menu.
            `);
        return message.channel.send({ embeds: [helpEmbed] });
    }

    if (message.content === '.rank') {
        const stats = getCommandStats();
        const sortedUsers = Object.entries(stats).sort((a, b) => b[1] - a[1]);
        
        const userIndex = sortedUsers.findIndex(([id]) => id === message.author.id);
        const userCount = stats[message.author.id] || 0;

        const rankEmbed = new EmbedBuilder()
            .setTitle('Your Leaderboard Rank')
            .setColor('Blurple')
            .setTimestamp();

        if (userIndex !== -1) {
            const rankPosition = userIndex + 1;
            const totalTrackedUsers = sortedUsers.length;
            rankEmbed.setDescription(
                `You are ranked **#${rankPosition}** out of **${totalTrackedUsers}** users with **${userCount}** command(s) used!`
            );
        } else {
            rankEmbed.setDescription(`You haven't used any tracked commands yet! (**0** commands used)`);
        }

        return message.reply({ embeds: [rankEmbed] });
    }

    if (message.content.startsWith('.compress')) {
        incrementCommandCount(message.author.id);
        let rawLua = null;
        const attachment = message.attachments.first();
        const codeBlockMatch = message.content.match(/```(?:[\w]*\n)?([\s\S]*?)```/);

        try {
            if (attachment) {
                const resp = await axios.get(attachment.url);
                rawLua = typeof resp.data === 'object' ? JSON.stringify(resp.data) : String(resp.data);
            } else if (codeBlockMatch) {
                rawLua = codeBlockMatch[1];
            } else {
                const parts = message.content.split(' ');
                if (parts.length > 1 && (parts[1].startsWith('http://') || parts[1].startsWith('https://'))) {
                    const resp = await axios.get(parts[1]);
                    rawLua = typeof resp.data === 'object' ? JSON.stringify(resp.data) : String(resp.data);
                }
            }
        } catch (e) {
            return message.reply("Failed to fetch attachment or URL.");
        }

        if (!rawLua || !rawLua.trim()) {
            return message.reply("Please attach a Lua file, provide a direct URL, or put code in a codeblock.");
        }

        try {
            const originalBuffer = Buffer.from(rawLua, 'utf8');
            const compressedBuffer = zlib.deflateSync(originalBuffer);
            const base64Data = compressedBuffer.toString('base64');

            const origSizeKB = (originalBuffer.length / 1024).toFixed(2);
            const compSizeKB = (compressedBuffer.length / 1024).toFixed(2);
            const ratio = (originalBuffer.length / Math.max(compressedBuffer.length, 1)).toFixed(2);

            const compressedScript = `local b=buffer;return loadstring(b.tostring((game:GetService('EncodingService') and game:GetService('EncodingService'):DecompressBuffer(b.fromstring(base64.decode("${base64Data}"))) or zlib.decompress(b.fromstring(base64.decode("${base64Data}"))))))()`;

            const rawPasteUrl = await uploadToPastefy(compressedScript);

            if (!rawPasteUrl) {
                return message.reply("Failed to upload the compressed payload to Pastefy.");
            }

            const responseText = `Successfully compressed! (${origSizeKB} KB -> ${compSizeKB} KB [${ratio}x])\n\n\`\`\`lua\nloadstring(game:HttpGetAsync("${rawPasteUrl}"))()\n\`\`\``;

            return message.reply({ content: responseText });
        } catch (e) {
            console.error("Compression error:", e);
            return message.reply("Failed to compress the provided script.");
        }
    }

    if (message.content.startsWith('.v2')) {
        incrementCommandCount(message.author.id);
        let luaContent = '';
        
        if (message.attachments.size > 0) {
            const attachment = message.attachments.first();
            if (attachment.name.endsWith('.lua') || attachment.name.endsWith('.txt')) {
                try {
                    const response = await axios.get(attachment.url);
                    luaContent = typeof response.data === 'object' ? JSON.stringify(response.data) : response.data;
                } catch (err) {
                    return message.reply('Failed to read the attached file.');
                }
            }
        } 
        else {
            const args = message.content.slice('.v2'.length).trim();
            if (!args) {
                return message.reply('Please provide a raw text link or upload a `.lua`/`.txt` file.');
            }

            if (args.startsWith('http://') || args.startsWith('https://')) {
                try {
                    const response = await axios.get(args);
                    luaContent = typeof response.data === 'object' ? JSON.stringify(response.data) : response.data;
                } catch (err) {
                    return message.reply('Failed to fetch content from the provided URL.');
                }
            } else {
                luaContent = args.replace(/^```lua|```$/g, '').trim(); 
            }
        }

        if (!luaContent) {
            return message.reply('Could not extract any valid text/Lua code.');
        }

        const uniqueId = Date.now();
        const inputName = `input_${uniqueId}.lua`;
        const outputName = `out_${uniqueId}.lua`;
        const inputPath = path.join(__dirname, inputName);
        const outputPath = path.join(__dirname, outputName);

        fs.writeFileSync(inputPath, luaContent, 'utf8');

        const statusMessage = await message.reply('Processing...');

        exec(`node run.js "${inputName}" "${outputName}"`, { cwd: __dirname, timeout: 15000 }, (error, stdout, stderr) => {
            if (fs.existsSync(inputPath)) fs.unlinkSync(inputPath);

            if (error) {
                console.error(`Execution error: ${error}`);
                if (stderr) console.error(`Stderr: ${stderr}`);
                statusMessage.edit('An error occurred while env logging.').catch(() => {});
                if (fs.existsSync(outputPath)) fs.unlinkSync(outputPath);
                return;
            }

            if (!fs.existsSync(outputPath)) {
                statusMessage.edit('Process finished but no output file (`dumped.lua`) was generated.').catch(() => {});
                return;
            }

            const attachment = new AttachmentBuilder(outputPath, { name: 'dumped.lua' });
            
            message.reply({
                content: `<@${message.author.id}> Here is your processed file:`,
                files: [attachment]
            }).then(() => {
                fs.unlinkSync(outputPath);
                statusMessage.delete().catch(() => {});
            }).catch((err) => {
                console.error(err);
                statusMessage.edit('Failed to send the output file.').catch(() => {});
                if (fs.existsSync(outputPath)) fs.unlinkSync(outputPath);
            });
        });
        
        return; 
    }

    if (message.content.startsWith('.get')) {
        incrementCommandCount(message.author.id);
        const parts = message.content.split(' ');
        if (parts.length < 2) {
            return message.reply("Please provide a valid URL. Usage: `.get <url>`");
        }

        const targetUrl = parts[1];
        
        try {
            const response = await axios.get(targetUrl);
            let responseData = response.data;

            if (typeof responseData === 'object') {
                responseData = JSON.stringify(responseData, null, 2);
            } else {
                responseData = String(responseData);
            }

            if (!responseData.trim()) {
                return message.reply("The website returned an empty response.");
            }

            if (responseData.length > 1900) {
                const link = await uploadToPastefy(responseData);
                return message.reply(`Response data too long, uploaded to: ${link}`);
            }

            return message.reply(`\`\`\`\n${responseData}\n\`\`\``);
        } catch (e) {
            return message.reply(`Failed to fetch data from the website. Error: ${e.message}`);
        }
    }

    if (message.content.startsWith(LUAMIN_PREFIX)) {
        incrementCommandCount(message.author.id);
        let content = null;
        const attachment = message.attachments.first();
        const codeBlockMatch = message.content.match(/```(?:[\w]*\n)?([\s\S]*?)```/);

        try {
            if (attachment) {
                const resp = await axios.get(attachment.url);
                content = resp.data;
            } else if (codeBlockMatch) {
                content = codeBlockMatch[1];
            } else {
                const parts = message.content.split(' ');
                if (parts.length > 1) {
                    const resp = await axios.get(parts[1]);
                    content = resp.data;
                }
            }
        } catch (e) {
            return message.reply("Failed to fetch the file or URL. Please ensure it is valid.");
        }

        if (!content) return message.reply("Provide a file, link, or codeblock.");
        
        try {
            const beautified = await beautify(content);
            if (beautified.length > 1900) {
                const link = await uploadToPastefy(beautified);
                return message.reply(`Output too long, uploaded to: ${link}`);
            }
            return message.reply(`\`\`\`lua\n${beautified}\n\`\`\``);
        } catch (e) { 
            console.error("Beautify error:", e);
            return message.reply("Failed to beautify."); 
        }
    }

    if (message.content.startsWith('.minify')) {
        incrementCommandCount(message.author.id);
        let content = null;
        const attachment = message.attachments.first();
        const codeBlockMatch = message.content.match(/```(?:[\w]*\n)?([\s\S]*?)```/);

        if (attachment) {
            try {
                const resp = await axios.get(attachment.url);
                content = resp.data;
            } catch (e) { return message.reply("Failed to fetch attachment."); }
        } else if (codeBlockMatch) {
            content = codeBlockMatch[1];
        }

        if (!content) return message.reply("Please provide a file or a codeblock.");
        
        try {
            const minified = luamin.Minify(content, { RenameVariables: false, RenameGlobals: false, SolveMath: false });
            
            if (minified.length > 1900) {
                const link = await uploadToPastefy(minified);
                return message.reply(`Output too long. Uploaded to: ${link}`);
            }
            return message.reply(`\`\`\`lua\n${minified}\n\`\`\``);
        } catch (e) { 
            return message.reply("Failed to minify the provided code."); 
        }
    }

    if (message.content.startsWith('.promdeobf')) {
        incrementCommandCount(message.author.id);
        let content = null;
        const attachment = message.attachments.first();
        const codeBlockMatch = message.content.match(/```(?:[\w]*\n)?([\s\S]*?)```/);

        if (attachment) {
            try {
                const response = await axios.get(attachment.url);
                content = response.data;
            } catch (e) { return message.reply("Failed to fetch attachment."); }
        } else if (codeBlockMatch) {
            content = codeBlockMatch[1];
        } else {
            const parts = message.content.split(' ');
            if (parts.length > 1) {
                try {
                    const response = await axios.get(parts[1]);
                    content = response.data;
                } catch (e) { return message.reply("Invalid link."); }
            }
        }

        if (!content) return message.reply("Please provide an attachment, codeblock, or link.");

        const baseDir = path.join(__dirname, 'promdeobf');
        const inputPath = path.join(baseDir, 'input.lua');
        const outputPath = path.join(baseDir, 'out.lua');

        try {
            fs.writeFileSync(inputPath, content);
        } catch (err) {
            return message.reply("Error writing input file.");
        }

        exec(`node main.js input.lua out.lua`, { cwd: baseDir }, async (error) => {
            if (error) {
                console.error(error);
                return message.reply("Error executing script.");
            }

            if (fs.existsSync(outputPath)) {
                const fileAttachment = new AttachmentBuilder(outputPath, { name: 'deobfuscated.lua' });
                
                return message.channel.send({ 
                    content: `<@${message.author.id}>, here is your deobfuscated file:`, 
                    files: [fileAttachment] 
                });
            } else {
                return message.reply("Command ran but no output file was created.");
            }
        });
    }

    if (message.content.startsWith('.webhook')) {
        incrementCommandCount(message.author.id);
        let contentToScan = message.content.replace('.webhook', '').trim();
        const attachment = message.attachments.first();

        if (attachment) {
            try {
                const response = await axios.get(attachment.url);
                contentToScan = typeof response.data === 'string' ? response.data : JSON.stringify(response.data);
            } catch (e) {
                return message.reply("Failed to read the attached file.");
            }
        }

        if (!contentToScan) {
            const helpEmbed = new EmbedBuilder()
                .setTitle('Webhook Scanner')
                .setColor('Blurple')
                .setDescription('Use `.webhook` with a codeblock or attach a file to scan for malicious Discord Webhooks.');
            return message.reply({ embeds: [helpEmbed] });
        }

        const found = contentToScan.match(webhookRegex);
        const embed = new EmbedBuilder();

        if (found) {
            embed.setTitle('Captured')
                .setColor('Blurple')
                .setDescription('**Webhook Captured**')
                .addFields({ name: 'Found Links:', value: found.join('\n') });
        } else {
            embed.setTitle('Detection Result')
            .setColor('#b33c3c')
                .setDescription('No webhook detected.');
        }

        message.reply({ embeds: [embed] });
    }

    if (message.content.startsWith(UPLOAD_PREFIX)) {
        incrementCommandCount(message.author.id);
        let contentToUpload = null;
        const attachment = message.attachments.first();
        const codeBlockMatch = message.content.match(/```(?:[\w]*\n)?([\s\S]*?)```/);

        if (attachment) {
            try {
                const response = await axios.get(attachment.url);
                contentToUpload = typeof response.data === 'object' ? JSON.stringify(response.data) : response.data;
            } catch (e) { return message.reply("Failed to fetch attachment."); }
        } else if (codeBlockMatch) {
            contentToUpload = codeBlockMatch[1];
        } else {
            const parts = message.content.split(' ');
            if (parts.length > 1) {
                try {
                    const response = await axios.get(parts[1]);
                    contentToUpload = response.data;
                } catch (e) { return message.reply("Invalid link or content."); }
            }
        }

        if (!contentToUpload) return message.reply("Please provide an attachment, a codeblock, or a valid URL.");

        const link = await uploadToPastefy(contentToUpload);
        if (link) {
            const embed = new EmbedBuilder()
                .setTitle('Uploaded')
                .setColor('Blurple')
                .setDescription(`[Click here to view the paste](${link})`);
            return message.channel.send({ embeds: [embed] });
        } else {
            return message.reply("Failed to upload to Pastefy.");
        }
    }

    if (message.content === '.leaderboard') {
        const stats = getCommandStats();
        const sortedUsers = Object.entries(stats)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 10);

        const embed = new EmbedBuilder()
            .setTitle('Command Usage Leaderboard')
            .setColor('Blurple')
            .setDescription(
                sortedUsers.length > 0
                    ? sortedUsers.map(([userId, count], index) => {
                          const medal = index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : `**#${index + 1}**`;
                          return `${medal} <@${userId}> — **${count}** commands`;
                        }).join('\n')
                    : 'No command usage recorded yet.'
            )
            .setTimestamp();

        return message.reply({ embeds: [embed] });
    }

    if (!message.content.startsWith(PREFIX)) return;
    if (message.channel.type !== 1 && message.channel.id !== ALLOWED_CHANNEL) return;

    incrementCommandCount(message.author.id);

    const attachment = message.attachments.first();
    let fileUrl = attachment ? attachment.url : null;
    let fileName = attachment ? attachment.name.split('.')[0] : null;

    if (!fileUrl && message.content.includes('http')) {
        fileUrl = message.content.split(' ').find(word => word.includes('http'));
        
        if (fileUrl) {
            fileName = fileUrl.split('/').pop().split('.')[0] || 'dump';
        } else {
            fileName = 'dump';
        }
    }

    if (!fileUrl) {
        const errorEmbed = new EmbedBuilder()
            .setTitle('Missing Input')
            .setColor('#b33c3c')
            .setDescription('Please provide a .lua or .txt file as an attachment, or include a valid raw link to a file.');
        return message.channel.send({ embeds: [errorEmbed] });
    }

    const startTime = Date.now();

    try {
        await message.react('😭');
        const response = await axios.get(fileUrl);
        const inputPath = path.join(__dirname, 'input.lua');
        const outputPath = path.join(__dirname, 'out.lua');
        
        fs.writeFileSync(inputPath, response.data);

        exec(`lune run main.luau input.lua out.lua`, { cwd: __dirname }, async (error) => {
            try {
                const endTime = Date.now();
                const timeTaken = ((endTime - startTime) / 1000).toFixed(2);
                
                if (error) {
                    await message.react('😭');
                    return message.reply('Error executing script.');
                }

                const finalFileName = `${fileName || 'output'}.dump.lua`;
                const rawContent = fs.readFileSync(outputPath, 'utf8');

                const foundLinks = rawContent.match(urlRegex);
                let linksText = "";
                
                if (foundLinks) {
                    const uniqueLinks = [...new Set(foundLinks)];
                    linksText = uniqueLinks.join('\n');
                }

                const fileAttachment = new AttachmentBuilder(outputPath, { name: finalFileName });
                const embed = new EmbedBuilder()
                    .setTitle('Process Complete')
                    .setColor('Blurple')
                    .addFields(
                        { name: 'Done', value: `<@${message.author.id}>` },
                        { name: 'File', value: String(finalFileName), inline: true },
                        { name: 'Time Taken', value: String(`${timeTaken}s`), inline: true },
                        { name: 'Status', value: 'Success', inline: true }
                    );

                if (linksText.length > 1900) {
                    const pasteLink = await uploadToPastefy(linksText);
                    embed.addFields({ name: 'Extracted Links', value: `[Too many links! Click here to view them all](${pasteLink})` });
                    linksText = ""; 
                }

                await message.channel.send({ 
                    content: linksText ? linksText : undefined,
                    embeds: [embed], 
                    files: [fileAttachment] 
                });
                
                await message.reactions.removeAll();
            } catch (err) {
                console.error("Exec callback error:", err);
                message.reply('An error occurred while preparing or sending the output.');
            }
        });
    } catch (err) {
        await message.react('😭');
        message.reply('Failed to process the file.');
    }
});

client.login(TOKEN);
