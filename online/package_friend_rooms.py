"""Add friend rooms and the IPv4 touch keypad to the iOS Quick Match package."""
from pathlib import Path
import plistlib
import sys
from zipfile import ZipFile

from patch import replace


def transport(source):
    source = replace(source, 'function network.start(state, host, address, relay_port)',
                     'function network.start(state, host, address, relay_port, room_mode, room_code)')
    source = replace(source, '    state.names, state.pending, state.sequence, state.frames = nil, nil, 0, 0',
                     '''    state.room_mode, state.join_code = room_mode, room_code
    state.names, state.pending, state.sequence, state.frames = nil, nil, 0, 0''')
    source = replace(source, '    state.phase, state.pending, state.received = "idle", nil, ""',
                     '''    state.phase, state.pending, state.received = "idle", nil, ""
    state.room_code, state.room_until = nil, nil''')
    start = '    if state.phase == "relay_connecting" and engine.network("status") == "connected" then'
    end = '    if state.phase == "connecting" and engine.network("status") == "connected" then'
    old = source[source.index(start):source.index(end)]
    return replace(source, old, '''    if state.phase == "relay_connecting" and engine.network("status") == "connected" then
        local request = state.profile
        if state.room_mode == "create" then request = "C" .. request
        elseif state.room_mode == "join" then request = "J" .. request .. state.join_code end
        if not send(state, request) then return nil, state.error end
        state.phase = state.room_mode == "create" and "room_code" or "relay_wait"
        state.deadline = engine.network_time() + (state.room_mode and timeout or 120000)
    end
    if state.phase == "room_code" then
        if #state.received > 0 and state.received:sub(1, 1) ~= "R" then
            return failed(state, "Invalid room reply")
        end
        local reply = take(state, 7)
        if not reply then return false end
        local code = reply:sub(2)
        if not code:match("^%d%d%d%d%d%d$") then return failed(state, "Invalid room reply") end
        state.room_code = code
        state.room_until = engine.network_time() + 300000
        state.deadline = state.room_until + 5000
        state.phase = "relay_wait"
    end
    if state.phase == "relay_wait" then
        local role = take(state, 1)
        if not role then return false end
        if state.room_mode == "create" and role == "T" then return failed(state, "Room expired") end
        if state.room_mode == "join" then
            if role == "N" then return failed(state, "Room not found or expired") end
            if role == "X" then return failed(state, "Both players need the same game version") end
        end
        if (role ~= "H" and role ~= "G") or (state.room_mode == "create" and role ~= "H")
            or (state.room_mode == "join" and role ~= "G") then
            return failed(state, "Invalid matchmaking reply")
        end
        state.host = role == "H"
        state.phase = "connecting"
        state.deadline = engine.network_time() + timeout
    end
''')


def lobby(source):
    source = replace(source, '    state.message, state.quick = nil, false',
                     '    state.message, state.relay_mode = nil, nil')
    marker = 'local function navigation_spec(page)'
    source = replace(source, marker, '''local create_target = navigation.target(259, 456, 399, 494)
local join_target = navigation.target(407, 456, 547, 494)
local room_keys, room_labels = {}, {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Delete", "Join", "Back"}
for index = 1, 12 do
    local col, row = (index - 1) % 3, math.floor((index - 1) / 3)
    local x, y = 230 + col * 114, 271 + row * 39
    room_keys[index] = navigation.target(x, y, x + 106, y + 35)
end
room_keys[13] = navigation.target(344, 430, 450, 465)

local function start_relay(state, mode)
    local room_mode = mode ~= "quick" and mode or nil
    if transport.start(state.session, false, relay_host, relay_port, room_mode, state.room_input) then
        state.page, state.message, state.relay_mode = "waiting", nil, mode
        state.started = engine.network_time()
    else state.message = state.session.error end
end

local function room_key(input, state)
    if not input.click then return false end
    for index, key in ipairs(room_keys) do
        if inside(input, key.left, key.top, key.right, key.bottom) then
            local label = room_labels[index]
            state.message = nil
            if label == "Back" then return true
            elseif label == "Delete" then state.room_input = state.room_input:sub(1, -2)
            elseif label == "Join" then
                if #state.room_input == 6 then start_relay(state, "join")
                else state.message = "Enter a 6-digit room code" end
            elseif #state.room_input < 6 then state.room_input = state.room_input .. label end
            return false
        end
    end
    return false
end

''' + marker)
    source = replace(source, '    local target = navigation.target\n',
                     '''    local target = navigation.target
    if page == "friend_join" then return {page = page, targets = room_keys} end
''')
    source = replace(source, 'quick_target}}', 'quick_target, create_target, join_target}}')
    source = replace(source, '            elseif problem then state.page, state.message = "choice", problem end',
                     '''            elseif problem then
                state.page = state.relay_mode == "join" and "friend_join" or "choice"
                state.message = problem
            end''')
    source = replace(source, '    elseif state.page == "join" then\n        for code', '''    elseif state.page == "friend_join" then
        cancel = input.nav.cancel or room_key(input, state)
    elseif state.page == "join" then
        for code''')
    source = replace(source, '''            if transport.start(state.session, false, relay_host, relay_port) then
                state.page, state.message, state.quick = "waiting", nil, true
                state.started = engine.network_time()
            else state.message = state.session.error end''', '''            start_relay(state, "quick")
        elseif input.click and inside(input, create_target.left, create_target.top, create_target.right, create_target.bottom) then
            sounds.direct(state, "ok")
            start_relay(state, "create")
        elseif input.click and inside(input, join_target.left, join_target.top, join_target.right, join_target.bottom) then
            sounds.direct(state, "ok")
            state.page, state.message, state.room_input = "friend_join", nil, ""''')
    source = replace(source, '        if state.page == "choice" then context.action("launch") else state.page = "choice" end',
                     '''        if state.page == "choice" then context.action("launch")
        elseif state.page == "waiting" and state.relay_mode == "join" then state.page = "friend_join"
        else state.page = "choice" end
        state.message, state.relay_mode = nil, nil''')
    source = replace(source, '    local function button(target, label)',
                     '    local function button(target, label, translation)')
    source = replace(source, 'font.gdi(context, label, target.x, target.y - 7, 0xffffff, nil, "center")',
                     'font.gdi(context, label, target.x, target.y - 7, 0xffffff, nil, "center", nil, translation)')
    source = replace(source, '    if state.page == "waiting" then\n        if state.quick then',
                     '''    if state.page == "friend_join" then
        context.fill(220, 206, 356, 268, 16, 33, 96)
        font.gdi(context, "Enter the room code", 398, 220, 0xffffff, nil, "center", nil, "輸入六位房號")
        font.gdi(context, state.room_input .. string.rep("_", 6 - #state.room_input), 398, 244, 0xffffff, nil, "center")
        local labels = {Delete = "刪除", Join = "加入", Back = "返回"}
        for index, target in ipairs(room_keys) do
            local label = room_labels[index]
            button(target, label, labels[label])
        end
    elseif state.page == "waiting" then
        if state.relay_mode then''')
    source = replace(source, '''            local label = phase == "relay_wait" and "Searching for an opponent..."
                or (phase == "relay_connecting" and "Connecting to matchmaking..." or "Starting match...")
            font.gdi(context, label, 397, 294, 0xffffff, nil, "center")''', '''            if phase == "relay_wait" and state.session.room_code then
                local left = math.max(0, math.ceil((state.session.room_until - engine.network_time()) / 1000))
                local countdown = string.format("%d:%02d", math.floor(left / 60), left % 60)
                local code = state.session.room_code
                font.gdi(context, "Room code: " .. code, 397, 288, 0xffffff, nil, "center", 22, "房號  " .. code)
                font.gdi(context, "Waiting for friend  " .. countdown, 397, 319, 0xffffff, nil, "center",
                    nil, "等待好友  " .. countdown)
            else
                local label, translation = "Starting match...", "正在進入連線遊戲"
                if phase == "relay_connecting" or phase == "room_code" then
                    label, translation = "Connecting to relay...", "正在連接中繼"
                elseif phase == "relay_wait" and state.relay_mode == "quick" then
                    label, translation = "Searching for an opponent...", "正在尋找對手"
                elseif phase == "relay_wait" then
                    label, translation = "Joining room...", "正在加入好友房"
                end
                font.gdi(context, label, 397, 294, 0xffffff, nil, "center", nil, translation)
            end''')
    source = replace(source, '        button(quick_target, "Quick Match")',
                     '''        button(quick_target, "Quick Match")
        button(create_target, "Create Room", "建立好友房")
        button(join_target, "Join Room", "加入好友房")''')
    return replace(source, '    if state.message then font.gdi(context, i18n.clip(state.message, 94), 10, 510) end',
                   '''    if state.message then
        local translated = ({
            ["Room expired"] = "好友房已逾時",
            ["Room not found or expired"] = "找不到房間，或房號已失效",
            ["Both players need the same game version"] = "雙方需要安裝同一版遊戲",
            ["Enter a 6-digit room code"] = "請輸入六位數房號",
        })[state.message]
        font.gdi(context, i18n.clip(state.message, 94), 397, 506, 0xffffff, nil, "center", nil, translated)
    end''')


def direct_ip_keypad(source):
    # Reuse the standalone lobby's keypad without overwriting the friend-room UI.
    keypad = (Path(__file__).resolve().parents[1] / 'ios-network/network.lua').read_text(encoding='utf-8')

    def section(script, start, end, *, after=''):
        first = script.index(start, script.index(after)) if after else script.index(start)
        return script[first:script.index(end, first + len(start))]

    nav_start = 'local function navigation_spec(page)'
    join_navigation = '    if page == "join" then\n'
    choice_targets = '    return {page = page, targets = {target(0x104,'
    source = replace(source, nav_start, section(keypad, '-- The IPv4 field', nav_start) + nav_start)
    source = replace(source, section(source, join_navigation, choice_targets),
                     section(keypad, join_navigation, choice_targets))
    source = replace(source, '-- The clickable areas for keyboard and controller navigation (base/ui/navigation); the join\n'
                     '-- page starts on its Connect button so Enter connects at once, as it always did.\n', '')

    keypad_update = section(keypad, '        for _, target in ipairs(keypad) do\n', '    else\n        cancel =')
    # Enter and controller A activate the highlighted button through navigation.apply.
    keypad_update = replace(keypad_update,
                            '        if not cancel and (flow_input.keys[virtual_keys.enter] and not state.previous_keys[virtual_keys.enter]\n'
                            '           or hit(input, connect)) then', '        if not cancel and hit(input, connect) then')
    source = replace(source, section(source, '        -- Text a soft keyboard', '    else\n        cancel ='), keypad_update)
    source = replace(source, ', keyboard = false', '')
    source = replace(source, section(source, '    -- The on-screen keyboard follows', '    for _, sound'), '')
    source = replace(source, '            state.page = "join"\n', '            state.page, state.message = "join", nil\n'
                     '            context.text_input(false)\n')

    join_draw = '    elseif state.page == "join" then\n'
    choice_draw = '    else\n'
    source = replace(source, section(source, join_draw, choice_draw, after='function screen.draw'),
                     section(keypad, join_draw, choice_draw, after='function screen.draw'))
    return replace(source, '            ["Enter a 6-digit room code"] = "請輸入六位數房號",',
                   '            ["Enter a 6-digit room code"] = "請輸入六位數房號",\n'
                   '            ["Enter a valid IPv4 address"] = "請輸入有效的 IPv4 位址",')


def package(source, output):
    app = 'Payload/openlf2.app/'
    base = app + 'scripts/base/'
    game, menu = base + 'game/network.lua', base + 'ui/network.lua'
    with ZipFile(source) as original, ZipFile(output, 'w') as updated:
        info = plistlib.loads(original.read(app + 'Info.plist'))
        assert info['CFBundleIdentifier'] == 'io.github.retrogamehub.lf2ultimate.network'
        edits = {
            game: transport(original.read(game).decode()).encode(),
            menu: direct_ip_keypad(lobby(original.read(menu).decode())).encode(),
        }
        for item in original.infolist():
            contents = edits[item.filename] if item.filename in edits else original.read(item)
            updated.writestr(item, contents)
    with ZipFile(output) as updated:
        assert updated.testzip() is None


if __name__ == '__main__':
    package(*sys.argv[1:])
