-- MiG-17 Level Acceleration Test Logger

local ACCEL_TEST = {}
local SPEED_GATES_MS  = { 200, 250, 280, 300 }        -- m/s
local SPEED_GATES_KT  = { 389, 486, 544, 583 }        -- knots

ACCEL_TEST.groupConfigs = {
  { name = "ACCEL_SL",   label = "SL"   },
  { name = "ACCEL_10K",  label = "10K"  },
  { name = "ACCEL_20K",  label = "20K"  },
}

ACCEL_TEST.samplePeriod = 1.0
ACCEL_TEST.stateByName  = {}

local function v3Len(v)   return math.sqrt(v.x*v.x + v.y*v.y + v.z*v.z) end
local function msToKt(ms) return ms * 1.943844 end
local function mToFt(m)   return m  * 3.28084 end

local function logInfo(msg)
  env.info("[ACCEL_TEST] " .. msg)
end

local function showMessage(msg, dur)
  trigger.action.outText("[ACCEL] " .. msg, dur or 10)
end

local function initState(cfg)
  local st = ACCEL_TEST.stateByName[cfg.name]
  if not st then
    st = { cfg = cfg, t0 = nil, gateTimes = {}, lastSample = nil }
    ACCEL_TEST.stateByName[cfg.name] = st
  end
  return st
end

local function updateGroup(state, now)
  local cfg = state.cfg
  local g   = Group.getByName(cfg.name)
  if not g then return end

  local units = g:getUnits()
  if not units or #units == 0 then return end

  local u = units[1]
  if not (u and u:isExist()) then return end

  local pt  = u:getPoint()
  local vel = u:getVelocity()
  if not (pt and vel) then return end

  local alt_ft = mToFt(pt.y or 0)
  local spd_ms = v3Len(vel)
  local spd_kt = msToKt(spd_ms)

  if not state.t0 then
    state.t0 = now
    logInfo(string.format("Group %s (%s) test started at t=%.1f", cfg.name, cfg.label, now))
    showMessage(string.format("%s accel test started", cfg.label), 5)
  end

  if (not state.lastSample) or (now - state.lastSample >= ACCEL_TEST.samplePeriod) then
    state.lastSample = now
    logInfo(string.format("%s t=%.1fs alt=%.0fft spd=%.1fkt",
                          cfg.label, now - state.t0, alt_ft, spd_kt))
  end

  for i, gateMs in ipairs(SPEED_GATES_MS) do
    if not state.gateTimes[i] and spd_ms >= gateMs then
      state.gateTimes[i] = now
      local dt     = now - state.t0
      local gateKt = SPEED_GATES_KT[i] or msToKt(gateMs)
      local msg = string.format(
        "%s crossed %.0f kt (%.0f m/s) at t=%.1fs from start, alt=%.0fft",
        cfg.label, gateKt, gateMs, dt, alt_ft
      )
      logInfo(msg)
      showMessage(msg, 10)
    end
  end
end

local function updateAll(args, time)
  local now = time or timer.getTime()
  for _, cfg in ipairs(ACCEL_TEST.groupConfigs) do
    local st = initState(cfg)
    updateGroup(st, now)
  end
  return now + ACCEL_TEST.samplePeriod
end

do
  logInfo("MiG-17 acceleration test script initializing.")
  timer.scheduleFunction(updateAll, {}, timer.getTime() + ACCEL_TEST.samplePeriod)
end
