"""Add quick matchmaking to the iOS test IPA while preserving direct connections."""
from pathlib import Path
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
local relay_host, relay_port = "viaduct.proxy.rlwy.net", 59934
''' + marker)
    source = replace(source, '        target(0x104, 0x150, 0x223, 0x169)}}',
                     '        target(0x104, 0x150, 0x223, 0x169), quick_target}}')
    source = replace(source, '    state.message = nil\n    if transport.start(state.session, host, address)',
                     '    state.message, state.quick = nil, false\n    if transport.start(state.session, host, address)')
    source = replace(source, '            state.page = "join"\n        end', '''            state.page = "join"
        elseif input.click and inside(input, quick_target.left, quick_target.top, quick_target.right, quick_target.bottom) then
            sounds.direct(state, "ok")
            if transport.start(state.session, false, relay_host, relay_port) then
                state.page, state.message, state.quick = "waiting", nil, true
                state.started = engine.network_time()
            else state.message = state.session.error end
        end''')
    source = replace(source, '    if state.page == "waiting" then\n        sprite(state.session.host and 10 or 11, 0xec, 0x122)', '''    local function button(target, label)
        local hovered = state.pointer_x >= target.left and state.pointer_x <= target.right
            and state.pointer_y >= target.top and state.pointer_y <= target.bottom
        context.fill(target.left, target.top, target.right - target.left, target.bottom - target.top,
            hovered and 54 or 33, hovered and 86 or 58, hovered and 166 or 131)
        font.gdi(context, label, target.x, target.y - 7, 0xffffff, nil, "center")
    end
    if state.page == "waiting" then
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


def package(source, output, executable):
    app = 'Payload/openlf2.app/'
    base = app + 'scripts/base/'
    info_name = app + 'Info.plist'
    with ZipFile(source) as original, ZipFile(output, 'w') as updated:
        info = plistlib.loads(original.read(info_name))
        assert info['CFBundleIdentifier'] == 'io.github.retrogamehub.lf2ultimate'
        info['CFBundleIdentifier'] = 'io.github.retrogamehub.lf2ultimate.network'
        info['CFBundleDisplayName'] = '終極 LF2 連線測試'
        info['NSLocalNetworkUsageDescription'] = '用於和同一區域網路上的玩家或測試伺服器連線。'
        edits = {
            info_name: plistlib.dumps(info),
            app + 'openlf2': Path(executable).read_bytes(),
        }
        for name, transform in [('game/network.lua', transport), ('ui/network.lua', lobby), ('ui/flow.lua', flow)]:
            edits[base + name] = transform(original.read(base + name).decode()).encode()
        for item in original.infolist():
            updated.writestr(item, edits[item.filename] if item.filename in edits else original.read(item))
    with ZipFile(output) as updated:
        assert updated.testzip() is None


if __name__ == '__main__':
    package(*sys.argv[1:])
