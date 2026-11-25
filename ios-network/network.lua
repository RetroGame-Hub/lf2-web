-- SPDX-License-Identifier: MIT
-- Copyright (c) 2026 OpenLF2 contributors

local transport = require("base/game/network")
local controls = require("base/ui/controls")
local font = require("base/ui/font")
local i18n = require("base/i18n/i18n")
local sounds = require("base/game/sounds")
local navigation = require("base/ui/navigation")
local constants = require("base/game/constants")
local virtual_keys = constants.virtual_keys
local screen = {}
local frames = {[1] = {0, 41, 434, 80}, [2] = {434, 41, 62, 68}, [3] = {0, 247, 304, 126}, [4] = {0, 376, 363, 123},
    [5] = {500, 42, 291, 27}, [6] = {500, 72, 291, 27}, [10] = {460, 203, 334, 108},
    [11] = {460, 313, 334, 108}, [12] = {643, 426, 151, 26}, [13] = {489, 426, 151, 26},
    [14] = {490, 462, 304, 38}}
local function inside(input, left, top, right, bottom)
    return input.pointer_x >= left and input.pointer_x <= right and input.pointer_y >= top and input.pointer_y <= bottom
end
function screen.create(options)
    return {session = transport.create(options), page = "choice", address = "", previous_keys = {},
        nav = navigation.create(),
        background = (options.menu_seed or 0) % 13 + 1, pointer_x = 0, pointer_y = 0,
        bind = options.network_bind or "0.0.0.0", started = engine.network_time()}
end
function screen.begin(state, host, address)
    state.message = nil
    if transport.start(state.session, host, address) then state.page = "waiting"
    else state.message = state.session.error end
    state.started = engine.network_time()
end
-- The IPv4 field uses an in-game keypad so the system keyboard cannot hide it.
local keypad = {}
local labels = {"1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "DEL"}
for index, label in ipairs(labels) do
    local left = 241 + ((index - 1) % 3) * 106
    local top = 298 + math.floor((index - 1) / 3) * 41
    local target = navigation.target(left, top, left + 98, top + 36)
    target.label = label
    keypad[#keypad + 1] = target
end
local connect = navigation.target(241, 464, 393, 506)
local back = navigation.target(401, 464, 551, 506)
local join_targets = {connect, back}
for _, target in ipairs(keypad) do join_targets[#join_targets + 1] = target end

local function hit(input, target)
    return input.click and inside(input, target.left, target.top, target.right, target.bottom)
end
local function edit(state, value)
    if value == "DEL" then state.address = state.address:sub(1, -2)
    elseif #state.address < 15 then state.address = state.address .. value end
    state.message = nil
end
local function ipv4(address)
    local a, b, c, d = address:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
    if not a then return end
    local parts = {tonumber(a), tonumber(b), tonumber(c), tonumber(d)}
    for _, octet in ipairs(parts) do if octet > 255 then return end end
    return table.concat(parts, ".")
end

local function navigation_spec(page)
    local target = navigation.target
    if page == "waiting" then return {page = page, targets = {target(0x142, 0x169, 0x1d8, 0x182)}} end
    if page == "join" then
        return {page = page,
            targets = join_targets}
    end
    return {page = page, targets = {target(0x104, 0x112, 0x223, 0x12c), target(0x104, 0x131, 0x223, 0x14a),
        target(0x104, 0x150, 0x223, 0x169)}}
end
function screen.update(state, flow_input, context)
    local input = navigation.apply(state.nav, flow_input, navigation_spec(state.page))
    state.pointer_x, state.pointer_y = input.pointer_x, input.pointer_y
    local cancel = input.nav.cancel
    if state.page == "waiting" then
        cancel = cancel or input.click and inside(input, 0x142, 0x169, 0x1d8, 0x182)
        if not cancel then
            local ready, problem = transport.poll(state.session)
            if ready then context.action("network_ready")
            elseif problem then state.page, state.message = "choice", problem end
        end
    elseif state.page == "join" then
        for code = 0, 255 do
            if input.keys[code] and not state.previous_keys[code] then
                if code == virtual_keys.backspace then state.address = state.address:sub(1, -2)
                else
                    local character = controls.key_character(code, false)
                    if character and character:match("^[%d.]$") and #state.address < 15 then state.address = state.address .. character end
                end
            end
        end
        for _, target in ipairs(keypad) do
            if hit(input, target) then edit(state, target.label); break end
        end
        cancel = cancel or hit(input, back)
        if not cancel and (flow_input.keys[virtual_keys.enter] and not state.previous_keys[virtual_keys.enter]
           or hit(input, connect)) then
            local address = ipv4(state.address)
            if address then screen.begin(state, false, address)
            else state.message = "Enter a valid IPv4 address" end
        end
    else
        cancel = cancel or input.click and inside(input, 0x104, 0x150, 0x223, 0x169)
        if input.click and inside(input, 0x104, 0x112, 0x223, 0x12c) then
            sounds.direct(state, "ok")
            screen.begin(state, true, state.bind)
        elseif input.click and inside(input, 0x104, 0x131, 0x223, 0x14a) then
            sounds.direct(state, "ok")
            state.page = "join"
            context.text_input(false)
        end
    end
    if cancel then
        transport.close(state.session)
        sounds.direct(state, "cancel")
        if state.page == "choice" then context.action("launch") else state.page = "choice" end
    end
    state.previous_keys = flow_input.keys
    for _, sound in ipairs(sounds.flush(state)) do context.sound(sound.resource, sound.volume, sound.pan) end
end
function screen.draw(state, context)
    local function sprite(frame, x, y) context.sprite("pe/menu_clip", frames[frame], x, y, true) end
    context.viewport(constants.screen.width, constants.screen.height, 16, 32, 108)
    context.image("pe/menu_back" .. state.background, 0, 0, true)
    -- The logo without the version in its bottom-right corner.
    sprite(1, 0x9b, 0x69)
    sprite(2, 0x9b + 434, 0x69)
    sprite(3, 0xfd, 0xde)
    sprite(14, 0xfd, 0x14f)
    -- The original writes " Your IP Address: <address>" here on an opaque box, which also hides
    -- the art's own label; OpenLF2 has no address to show, so it shows its TCP port instead.
    font.gdi(context, " " .. i18n.tr("Your TCP port: %s", state.session.port), 0x121, 0xfb, 0xffffff, 0x001e50)
    if state.page == "waiting" then
        sprite(state.session.host and 10 or 11, 0xec, 0x122)
        sprite(12, 0x142, 0x169)
        local count = math.floor((engine.network_time() - state.started) / 150) % 14
        for index = 0, count - 1 do context.fill(0x119 + index * 20, 0x156, 5, 12, 87, 127, 215) end
    elseif state.page == "join" then
        context.fill(225, 242, 340, 278, 12, 29, 79)
        font.gdi(context, "Host IPv4", 241, 252, 0xffffff)
        font.gdi(context, state.address .. "_", 241, 274, 0xffffff, 0x001e50)
        local pointer = {pointer_x = state.pointer_x, pointer_y = state.pointer_y}
        local function key(target, label)
            local over = inside(pointer, target.left, target.top, target.right, target.bottom)
            context.fill(target.left, target.top, target.right - target.left, target.bottom - target.top,
                over and 50 or 30, over and 80 or 51, over and 146 or 106)
            font.gdi(context, label, target.x, target.y - 8, 0xffffff, nil, "center")
        end
        for _, target in ipairs(keypad) do key(target, target.label) end
        key(connect, "Connect")
        key(back, "Back")
    else
        local input = {pointer_x = state.pointer_x, pointer_y = state.pointer_y}
        if inside(input, 0x104, 0x112, 0x223, 0x12c) then sprite(5, 0x103, 0x112) end
        if inside(input, 0x104, 0x131, 0x223, 0x14a) then sprite(6, 0x103, 0x130) end
        if inside(input, 0x104, 0x150, 0x223, 0x169) then sprite(12, 0x149, 0x150) end
    end
    if state.message then font.gdi(context, i18n.clip(state.message, 94), 10, 510) end
    context.image("pe/lf2_cursor", math.min(state.pointer_x, 0x307), math.min(state.pointer_y + 2, 0x217), true)
end
function screen.describe(state)
    return "network_page=" .. state.page .. " phase=" .. state.session.phase .. (state.message and " error=" .. state.message or "")
end
return screen
