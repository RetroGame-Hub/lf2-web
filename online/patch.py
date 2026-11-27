"""Add quick matchmaking to the iOS test IPA while preserving direct connections."""
import plistlib
import sys
from zipfile import ZipFile


def replace(source, before, after):
    if source.count(before) != 1:
        raise ValueError(f"Unexpected source around {before!r}")
    return source.replace(before, after)


def transport(source):
    source = replace(source, 'function network.start(state, host, address)', 'function network.start(state, host, address, relay_port)')
    source = replace(source, 'address, state.port)', 'address, relay_port or state.port)')
    source = replace(source, '    state.phase = "connecting"', '    state.phase = relay_port and "relay_connecting" or "connecting"')
    marker = '    if state.phase == "connecting" and engine.network("status") == "connected" then'
    return replace(source, marker, '''    if state.phase == "relay_connecting" and engine.network("status") == "connected" then
        if not send(state, state.profile) then return nil, state.error end
        state.phase = "relay_wait"
        state.deadline = engine.network_time() + 120000
    end
    if state.phase == "relay_wait" then
        local role = take(state, 1)
        if not role then return false end
        if role ~= "H" and role ~= "G" then return failed(state, "Invalid matchmaking reply") end
        state.host = role == "H"
        state.phase = "connecting"
        state.deadline = engine.network_time() + timeout
    end
''' + marker)


def lobby(source):
    marker = 'local function navigation_spec(page)'
    source = replace(source, marker, '''local quick_target = navigation.target(259, 413, 547, 448)
local keypad = {}
local labels = {"1", "2", "3", ".", "4", "5", "6", ":", "7", "8", "9", "Delete", "Back", "0", "Clear", "Match"}
for index, label in ipairs(labels) do
    local col, row = (index - 1) % 4, math.floor((index - 1) / 4)
    keypad[index] = navigation.target(198 + col * 101, 225 + row * 54, 292 + col * 101, 272 + row * 54)
end
local function relay_endpoint(endpoint)
    local address, port = endpoint:match("^([%d.]+):(%d+)$")
    if not address and endpoint:match("^[%d.]+$") then address, port = endpoint, "12346" end
    port = tonumber(port)
    if not address or not port or port < 1 or port > 65535 then return nil end
    local a, b, c, d = address:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
    if not a then return nil end
    for _, part in ipairs({a,b,c,d}) do
        if #part > 3 or (#part > 1 and part:sub(1, 1) == "0") or tonumber(part) > 255 then return nil end
    end
    return address, port
end
local function navigation_spec(page)''')
    source = replace(source, '    if page == "waiting" then return', '''    if page == "relay" then return {page = page, targets = keypad} end
    if page == "waiting" then return''')
    source = replace(source, '        target(0x104, 0x150, 0x223, 0x169)}}', '        target(0x104, 0x150, 0x223, 0x169), quick_target}}')
    source = replace(source, 'nav = navigation.create(), keyboard = false,', 'nav = navigation.create(), keyboard = false, relay_address = "",')
    source = replace(source, '            elseif problem then state.page, state.message = "choice", problem end',
                     '            elseif problem then state.page, state.message = state.quick and "relay" or "choice", problem end')
    source = replace(source, '    elseif state.page == "join" then\n        for code', '''    elseif state.page == "relay" then
        if input.click then
            for index, target in ipairs(keypad) do
                if inside(input, target.left, target.top, target.right, target.bottom) then
                    local label = labels[index]
                    if label == "Back" then cancel = true
                    elseif label == "Delete" then state.relay_address = state.relay_address:sub(1, -2)
                    elseif label == "Clear" then state.relay_address = ""
                    elseif label == "Match" then
                        local address, port = relay_endpoint(state.relay_address)
                        if not address then state.message = "Enter a valid server IPv4 address and port."
                        elseif transport.start(state.session, false, address, port) then
                            state.page, state.message, state.quick = "waiting", nil, true
                            state.started = engine.network_time()
                        else state.message = state.session.error end
                    elseif #state.relay_address < 21 then
                        state.relay_address = state.relay_address .. label
                        state.message = nil
                    end
                    break
                end
            end
        end
    elseif state.page == "join" then
        for code''')
    source = replace(source, '    state.message = nil\n    if transport.start(state.session, host, address)', '    state.message, state.quick = nil, false\n    if transport.start(state.session, host, address)')
    source = replace(source, '            state.page = "join"\n        end', '''            state.page = "join"
        elseif input.click and inside(input, quick_target.left, quick_target.top, quick_target.right, quick_target.bottom) then
            state.page, state.message = "relay", nil
        end''')
    source = replace(source, '        if state.page == "choice" then context.action("launch") else state.page = "choice" end',
                     '''        if state.page == "choice" then context.action("launch")
        elseif state.page == "waiting" and state.quick then state.page = "relay"
        else state.page, state.message = "choice", nil end''')
    source = replace(source, '    if state.page == "waiting" then\n        sprite(state.session.host and 10 or 11, 0xec, 0x122)', '''    local function button(target, label)
        local hovered = state.pointer_x >= target.left and state.pointer_x <= target.right
            and state.pointer_y >= target.top and state.pointer_y <= target.bottom
        context.fill(target.left, target.top, target.right - target.left, target.bottom - target.top,
            hovered and 54 or 33, hovered and 86 or 58, hovered and 166 or 131)
        font.gdi(context, label, target.x, target.y - 7, 0xffffff, nil, "center")
    end
    if state.page == "relay" then
        context.fill(183, 144, 425, 306, 16, 33, 96)
        font.gdi(context, "Matchmaking server", 395, 153, 0xffffff, nil, "center")
        font.gdi(context, state.relay_address == "" and "Server IPv4[:port]" or state.relay_address .. "_",
            395, 184, 0xffffff, nil, "center")
        for index, target in ipairs(keypad) do button(target, labels[index]) end
    elseif state.page == "waiting" then
        if state.quick then
            context.fill(235, 280, 325, 75, 16, 33, 96)
            local phase = state.session.phase
            local label = phase == "relay_wait" and "Searching for an opponent..."
                or (phase == "relay_connecting" and "Connecting to matchmaking..." or "Starting match...")
            font.gdi(context, label, 397, 294, 0xffffff, nil, "center")
        else sprite(state.session.host and 10 or 11, 0xec, 0x122) end''')
    return replace(source, '        local input = {pointer_x = state.pointer_x, pointer_y = state.pointer_y}', '''        button(quick_target, "Quick Match")
        local input = {pointer_x = state.pointer_x, pointer_y = state.pointer_y}''')



def flow(source):
    return replace(source,
        '    local fighter = state.active == "match" and state.match and state.match.match and state.match.match.items[0] or nil',
        '''    local local_slot = state.session and not state.session.host and 4 or 0
    local fighter = state.active == "match" and state.match and state.match.match and state.match.match.items[local_slot] or nil''')


def package(source, output):
    app = 'Payload/openlf2.app/'
    base = app + 'scripts/base/'
    info_name = app + 'Info.plist'
    with ZipFile(source) as original, ZipFile(output, 'w') as updated:
        info = plistlib.loads(original.read(info_name))
        assert info['CFBundleIdentifier'] == 'io.github.retrogamehub.lf2ultimate'
        info['CFBundleIdentifier'] = 'io.github.retrogamehub.lf2ultimate.network'
        info['CFBundleDisplayName'] = '終極 LF2 連線測試'
        info['NSLocalNetworkUsageDescription'] = '用於和同一區域網路上的玩家或測試伺服器連線。'
        edits = {info_name: plistlib.dumps(info)}
        for name, transform in [('game/network.lua', transport), ('ui/network.lua', lobby), ('ui/flow.lua', flow)]:
            edits[base + name] = transform(original.read(base + name).decode()).encode()
        for item in original.infolist():
            updated.writestr(item, edits[item.filename] if item.filename in edits else original.read(item))
    with ZipFile(output) as updated:
        assert updated.testzip() is None


if __name__ == '__main__':
    package(*sys.argv[1:])
