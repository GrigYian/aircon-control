import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeftRight,
  ArrowUpDown,
  ChevronDown,
  ChevronUp,
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudLightning,
  CloudMoon,
  CloudRain,
  CloudSnow,
  CloudSun,
  Droplets,
  Fan,
  Heart,
  House,
  Leaf,
  Lightbulb,
  MapPin,
  Minus,
  Moon,
  Plus,
  Power,
  RefreshCw,
  Settings,
  ShieldCheck,
  Snowflake,
  Sparkles,
  Sun,
  ThermometerSnowflake,
  Waves,
  Wind,
  X,
  Zap,
} from 'lucide-react'

const MODES = [
  { label: 'Cool', value: 'COOL', icon: Snowflake },
  { label: 'Dry', value: 'DRY', icon: Droplets },
  { label: 'Fan Only', value: 'FAN_ONLY', icon: Fan },
  { label: 'Heat', value: 'HEAT', icon: Sun },
]

const FAN_SPEEDS = [
  { label: 'Auto', value: 'AUTO' },
  { label: 'Low', value: 'LOW' },
  { label: 'Medium', value: 'MEDIUM' },
  { label: 'High', value: 'HIGH' },
]

const MODE_VALUE_BY_LABEL = Object.fromEntries(MODES.map(({ label, value }) => [label, value]))
const FAN_VALUE_BY_LABEL = Object.fromEntries(FAN_SPEEDS.map(({ label, value }) => [label, value]))

const FEATURES = [
  { key: 'vertical_swing', label: 'Vertical', icon: ArrowUpDown },
  { key: 'horizontal_swing', label: 'Horizontal', icon: ArrowLeftRight },
  { key: 'eco', label: 'Eco', icon: Leaf },
  { key: 'turbo', label: 'Turbo', icon: Zap },
  { key: 'frost_protect', label: '8°C heat', icon: ThermometerSnowflake },
  { key: 'display_on', label: 'Display', icon: Lightbulb },
  { key: 'sleep', label: 'Sleep', icon: Moon },
  { key: 'comfort', label: 'Comfort', icon: Heart },
  { key: 'purifier', label: 'Purifier', icon: Sparkles },
  { key: 'dryer', label: 'Dryer', icon: Waves },
]

const ARC = { cx: 220, cy: 154, radius: 133, start: 140, sweep: 260 }
const WEATHER_REFRESH_MS = 30 * 60 * 1000

function weatherAppearance(code, isDay) {
  if (code === 0) return { icon: isDay ? Sun : Moon, label: 'Clear sky' }
  if (code === 1 || code === 2) {
    return { icon: isDay ? CloudSun : CloudMoon, label: 'Partly cloudy' }
  }
  if (code === 3) return { icon: Cloud, label: 'Overcast' }
  if (code === 45 || code === 48) return { icon: CloudFog, label: 'Fog' }
  if ([51, 53, 55, 56, 57].includes(code)) {
    return { icon: CloudDrizzle, label: 'Drizzle' }
  }
  if ([61, 63, 65, 66, 67, 80, 81, 82].includes(code)) {
    return { icon: CloudRain, label: 'Rain' }
  }
  if ([71, 73, 75, 77, 85, 86].includes(code)) {
    return { icon: CloudSnow, label: 'Snow' }
  }
  if ([95, 96, 99].includes(code)) {
    return { icon: CloudLightning, label: 'Thunderstorm' }
  }
  return { icon: CloudSun, label: 'Current weather' }
}

function arcPoint(angle) {
  const radians = (angle * Math.PI) / 180
  return {
    x: ARC.cx + ARC.radius * Math.cos(radians),
    y: ARC.cy + ARC.radius * Math.sin(radians),
  }
}

const ARC_START = arcPoint(ARC.start)
const ARC_END = arcPoint(ARC.start + ARC.sweep)
const ARC_PATH = `M ${ARC_START.x} ${ARC_START.y} A ${ARC.radius} ${ARC.radius} 0 1 1 ${ARC_END.x} ${ARC_END.y}`

function UiIcon({ icon: Icon, size = 20, className = '' }) {
  return <Icon className={className} size={size} strokeWidth={1.8} aria-hidden="true" />
}

function withOptimisticChanges(current, changes) {
  if (!current) return current
  const next = { ...current }
  if ('power' in changes) next.power = Boolean(changes.power)
  if ('temperature' in changes) next.target_temperature = Number(changes.temperature)
  if ('mode' in changes) {
    next.mode = MODE_VALUE_BY_LABEL[changes.mode] ?? next.mode
    if (current.mode === 'DRY' && next.mode !== 'DRY' && !('fan_speed' in changes)) {
      next.fan_speed = 'AUTO'
    }
  }
  if ('fan_speed' in changes) {
    next.fan_speed = FAN_VALUE_BY_LABEL[changes.fan_speed] ?? next.fan_speed
  }
  for (const { key } of FEATURES) {
    if (key in changes) next[key] = Boolean(changes[key])
  }
  return next
}

function SettingsDialog({ initial, saving, error, onClose, onSave }) {
  const [form, setForm] = useState(null)

  useEffect(() => {
    if (!initial) return
    setForm({
      account: initial.account ?? '',
      password: '',
      region: initial.region ?? 'DE',
      account_cloud: initial.account_cloud ?? 'NetHome Plus',
      device_ip: initial.device_ip ?? '',
      device_port: String(initial.device_port ?? 6444),
      device_id: initial.device_id ?? '',
      device_token: '',
      device_key: '',
      discovery_target: initial.discovery_target ?? '255.255.255.255',
      clear_local_credentials: false,
      weather_location_enabled: initial.weather_location_enabled ?? true,
      refresh_weather_location: false,
    })
  }, [initial])

  if (!form) return null
  const update = (name, value) => setForm((current) => ({ ...current, [name]: value }))

  return (
    <div className="settings-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !saving) onClose()
    }}>
      <section className="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <header>
          <div>
            <span className="settings-eyebrow">Device setup</span>
            <h2 id="settings-title">Connect your air conditioner</h2>
          </div>
          <button className="settings-close" onClick={onClose} disabled={saving} aria-label="Close settings">
            <UiIcon icon={X} size={20} />
          </button>
        </header>

        <p className="settings-intro">
          Use the same account and app that paired the AC. NetHome Plus can usually find a single linked unit automatically.
        </p>

        <form onSubmit={(event) => {
          event.preventDefault()
          onSave(form)
        }}>
        <div className="location-setting">
          <div className="location-setting__icon">
            <UiIcon icon={MapPin} size={19} />
          </div>
          <div className="location-setting__copy">
            <strong>Location-based weather</strong>
            <span>Use an approximate location to show the current outdoor weather icon.</span>
            {initial.weather_location && form.weather_location_enabled && (
              <small>Approximate location saved on this PC</small>
            )}
          </div>
          <label className="settings-switch" aria-label="Use device location for weather">
            <input
              type="checkbox"
              checked={form.weather_location_enabled}
              onChange={(event) => update('weather_location_enabled', event.target.checked)}
            />
            <span aria-hidden="true" />
          </label>
        </div>
        {form.weather_location_enabled && initial.weather_location && (
          <label className="refresh-location">
            <input
              type="checkbox"
              checked={form.refresh_weather_location}
              onChange={(event) => update('refresh_weather_location', event.target.checked)}
            />
            <span>Update the saved location after saving</span>
          </label>
        )}

          <div className="settings-grid">
            <label>
              <span>Mobile app</span>
              <select value={form.account_cloud} onChange={(event) => update('account_cloud', event.target.value)}>
                {initial.account_clouds.map((cloud) => <option key={cloud}>{cloud}</option>)}
              </select>
            </label>
            <label>
              <span>Account region</span>
              <select value={form.region} onChange={(event) => update('region', event.target.value)}>
                <option value="DE">Europe</option>
                <option value="US">United States</option>
                <option value="KR">Korea</option>
              </select>
            </label>
            <label className="wide">
              <span>Account email</span>
              <input
                type="email"
                value={form.account}
                onChange={(event) => update('account', event.target.value)}
                placeholder="name@example.com"
                autoComplete="username"
              />
            </label>
            <label className="wide">
              <span>Password</span>
              <input
                type="password"
                value={form.password}
                onChange={(event) => update('password', event.target.value)}
                placeholder={initial.has_password ? 'Saved — leave blank to keep it' : 'Mobile app password'}
                autoComplete="current-password"
              />
            </label>
            <label>
              <span>Device IP <small>optional</small></span>
              <input value={form.device_ip} onChange={(event) => update('device_ip', event.target.value)} placeholder="Automatic" />
            </label>
            <label>
              <span>Device ID <small>optional</small></span>
              <input value={form.device_id} onChange={(event) => update('device_id', event.target.value)} placeholder="Automatic" inputMode="numeric" />
            </label>
          </div>

          <details className="advanced-settings">
            <summary>Advanced local connection</summary>
            <div className="settings-grid advanced-grid">
              <label>
                <span>Device port</span>
                <input value={form.device_port} onChange={(event) => update('device_port', event.target.value)} inputMode="numeric" />
              </label>
              <label>
                <span>Discovery target</span>
                <input value={form.discovery_target} onChange={(event) => update('discovery_target', event.target.value)} />
              </label>
              <label>
                <span>Local token</span>
                <input type="password" value={form.device_token} onChange={(event) => update('device_token', event.target.value)} placeholder={initial.has_local_credentials ? 'Saved' : 'Optional'} autoComplete="off" />
              </label>
              <label>
                <span>Local key</span>
                <input type="password" value={form.device_key} onChange={(event) => update('device_key', event.target.value)} placeholder={initial.has_local_credentials ? 'Saved' : 'Optional'} autoComplete="off" />
              </label>
              {initial.has_local_credentials && (
                <label className="clear-credentials wide">
                  <input type="checkbox" checked={form.clear_local_credentials} onChange={(event) => update('clear_local_credentials', event.target.checked)} />
                  <span>Forget the saved local token and key</span>
                </label>
              )}
            </div>
          </details>

          {error && <div className="settings-error">{error}</div>}
          <div className="settings-privacy">
            <UiIcon icon={ShieldCheck} size={17} />
            Credentials stay in this Windows user’s local app-data folder and are never included in the application package.
          </div>
          <div className="settings-actions">
            <button type="button" className="settings-cancel" onClick={onClose} disabled={saving}>Cancel</button>
            <button type="submit" className="settings-save" disabled={saving}>{saving ? 'Saving…' : 'Save and connect'}</button>
          </div>
        </form>
      </section>
    </div>
  )
}

function TemperatureDial({ state, disabled, onCommit }) {
  const svgRef = useRef(null)
  const draggingRef = useRef(false)
  const [preview, setPreview] = useState(null)
  const minimum = state?.minimum_temperature ?? 16
  const maximum = state?.maximum_temperature ?? 31
  const temperature = preview ?? state?.target_temperature ?? 24
  const fraction = Math.max(0, Math.min(1, (temperature - minimum) / (maximum - minimum)))
  const knob = arcPoint(ARC.start + ARC.sweep * fraction)

  useEffect(() => setPreview(null), [state?.target_temperature])

  const temperatureAtPointer = useCallback(
    (event) => {
      const svg = svgRef.current
      if (!svg) return temperature
      const bounds = svg.getBoundingClientRect()
      const x = ((event.clientX - bounds.left) / bounds.width) * 440
      const y = ((event.clientY - bounds.top) / bounds.height) * 310
      let angle = (Math.atan2(y - ARC.cy, x - ARC.cx) * 180) / Math.PI
      if (angle < ARC.start) angle += 360
      angle = Math.max(ARC.start, Math.min(ARC.start + ARC.sweep, angle))
      const pointerFraction = (angle - ARC.start) / ARC.sweep
      return Math.round(minimum + pointerFraction * (maximum - minimum))
    },
    [maximum, minimum, temperature],
  )

  const beginDrag = (event) => {
    if (disabled) return
    draggingRef.current = true
    event.currentTarget.setPointerCapture(event.pointerId)
    setPreview(temperatureAtPointer(event))
  }

  const moveDrag = (event) => {
    if (draggingRef.current) setPreview(temperatureAtPointer(event))
  }

  const finishDrag = (event) => {
    if (!draggingRef.current) return
    const selected = temperatureAtPointer(event)
    draggingRef.current = false
    setPreview(selected)
    if (selected !== state.target_temperature) onCommit(selected)
  }

  const step = (change) => {
    const selected = Math.max(minimum, Math.min(maximum, temperature + change))
    setPreview(selected)
    if (selected !== state.target_temperature) onCommit(selected)
  }

  return (
    <section className="dial" aria-label="Temperature control">
      <svg
        ref={svgRef}
        className={`dial__svg ${disabled ? 'is-disabled' : ''}`}
        viewBox="0 0 440 310"
        onPointerDown={beginDrag}
        onPointerMove={moveDrag}
        onPointerUp={finishDrag}
        onPointerCancel={() => {
          draggingRef.current = false
          setPreview(null)
        }}
      >
        <path className="dial__track" d={ARC_PATH} pathLength="100" />
        <path
          className="dial__progress"
          d={ARC_PATH}
          pathLength="100"
          strokeDasharray={`${fraction * 100} 100`}
        />
        <path className="dial__hit-area" d={ARC_PATH} />
        <circle className="dial__knob" cx={knob.x} cy={knob.y} r="11" />
      </svg>

      <div className="dial__readout">
        <button
          className="round-step"
          disabled={disabled || temperature <= minimum}
          onClick={() => step(-1)}
          aria-label="Decrease temperature"
        >
          <UiIcon icon={Minus} size={22} />
        </button>
        <div className="temperature">{Math.round(temperature)}<small>°C</small></div>
        <button
          className="round-step"
          disabled={disabled || temperature >= maximum}
          onClick={() => step(1)}
          aria-label="Increase temperature"
        >
          <UiIcon icon={Plus} size={22} />
        </button>
      </div>
      <div className="fan-summary">
        Fan&nbsp; {state?.fan_speed?.replaceAll('_', ' ').toLowerCase() ?? '—'}
      </div>
      <span className="dial__minimum">{minimum}°C</span>
      <span className="dial__maximum">{maximum}°C</span>
    </section>
  )
}

function App() {
  const backgroundRefreshRef = useRef(false)
  const commandLoopRef = useRef(false)
  const queuedChangesRef = useRef({})
  const weatherLocationRef = useRef(null)
  const [state, setState] = useState(null)
  const [status, setStatus] = useState('Connecting')
  const [detail, setDetail] = useState('Starting the controller…')
  const [busy, setBusy] = useState(true)
  const [connectionOpen, setConnectionOpen] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsConfig, setSettingsConfig] = useState(null)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsError, setSettingsError] = useState('')
  const [weather, setWeather] = useState({ icon: CloudSun, label: 'Weather unavailable' })
  const [weatherLocationEnabled, setWeatherLocationEnabled] = useState(false)
  const [weatherSettingsReady, setWeatherSettingsReady] = useState(false)
  const [weatherRevision, setWeatherRevision] = useState(0)

  const applyWeatherSettings = useCallback((settings) => {
    const enabled = Boolean(settings?.weather_location_enabled)
    const location = settings?.weather_location
    weatherLocationRef.current = enabled && location
      ? { latitude: Number(location.latitude), longitude: Number(location.longitude) }
      : null
    setWeatherLocationEnabled(enabled)
    setWeatherSettingsReady(true)
    if (!enabled) {
      setWeather({ icon: CloudSun, label: 'Location weather off' })
    }
  }, [])

  const persistWeatherLocation = useCallback(async (values) => {
    const api = window.pywebview?.api
    if (!api) return null
    try {
      const response = await api.save_weather_location(values)
      if (!response.ok) throw new Error(response.error)
      setSettingsConfig((current) => current
        ? { ...current, ...response.settings }
        : current)
      applyWeatherSettings(response.settings)
      return response.settings
    } catch (error) {
      console.warn('Could not save weather location:', error)
      return null
    }
  }, [applyWeatherSettings])

  const fetchWeatherAt = useCallback(async (latitude, longitude) => {
    try {
      // Three decimal places are more than sufficient for a weather grid and
      // avoid sending unnecessarily precise device coordinates.
      const parameters = new URLSearchParams({
        latitude: latitude.toFixed(3),
        longitude: longitude.toFixed(3),
        current: 'weather_code,is_day',
        timezone: 'auto',
      })
      const response = await fetch(`https://api.open-meteo.com/v1/forecast?${parameters}`)
      if (!response.ok) throw new Error(`Weather request failed (${response.status})`)
      const payload = await response.json()
      if (payload.current) {
        setWeather(weatherAppearance(payload.current.weather_code, payload.current.is_day === 1))
        return true
      }
    } catch (error) {
      console.warn('Weather refresh failed:', error)
    }
    setWeather({ icon: CloudSun, label: 'Weather unavailable' })
    return false
  }, [])

  const refreshWeather = useCallback(async () => {
    if (!weatherLocationEnabled) {
      setWeather({ icon: CloudSun, label: 'Location weather off' })
      return false
    }
    const savedLocation = weatherLocationRef.current
    if (savedLocation) {
      return fetchWeatherAt(savedLocation.latitude, savedLocation.longitude)
    }
    if (!navigator.geolocation) {
      setWeather({ icon: CloudSun, label: 'Location unavailable' })
      return false
    }

    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        ({ coords }) => {
          const location = {
            latitude: Number(coords.latitude.toFixed(3)),
            longitude: Number(coords.longitude.toFixed(3)),
          }
          weatherLocationRef.current = location
          void persistWeatherLocation({ enabled: true, ...location })
          resolve(fetchWeatherAt(location.latitude, location.longitude))
        },
        (error) => {
          setWeather({ icon: CloudSun, label: 'Location unavailable' })
          if (error?.code === 1) {
            weatherLocationRef.current = null
            setWeatherLocationEnabled(false)
            void persistWeatherLocation({ enabled: false })
          }
          resolve(false)
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: WEATHER_REFRESH_MS },
      )
    })
  }, [fetchWeatherAt, persistWeatherLocation, weatherLocationEnabled])

  const callApi = useCallback(async (
    method,
    argument,
    { silent = false, commitState = true } = {},
  ) => {
    const api = window.pywebview?.api
    if (!api) return null
    if (!silent) {
      setBusy(true)
      setDetail(method === 'connect' ? 'Connecting to your AC…' : 'Sending command…')
    }
    try {
      const response = argument === undefined
        ? await api[method]()
        : await api[method](argument)
      if (!response.ok) throw new Error(response.error)
      if (commitState) setState(response.state)
      if (!silent) {
        setStatus(`Connected to ${response.state.ip}`)
        setDetail(response.state.transport === 'Local' ? 'Local control is ready' : 'NetHome Plus cloud control is ready')
      }
      return response.state
    } catch (error) {
      if (silent) {
        console.warn('Background AC refresh failed:', error)
      } else {
        setStatus('Disconnected')
        setDetail(error?.message || String(error))
      }
      return null
    } finally {
      if (!silent) setBusy(false)
    }
  }, [])

  const readSettings = useCallback(async () => {
    const api = window.pywebview?.api
    if (!api) return null
    try {
      const response = await api.get_settings()
      if (!response.ok) throw new Error(response.error)
      setSettingsConfig(response.settings)
      applyWeatherSettings(response.settings)
      return response.settings
    } catch (error) {
      setSettingsError(error?.message || String(error))
      return null
    }
  }, [applyWeatherSettings])

  const openSettings = useCallback(async () => {
    setSettingsError('')
    const config = await readSettings()
    if (config) setSettingsOpen(true)
  }, [readSettings])

  const saveSettings = useCallback(async (values) => {
    const api = window.pywebview?.api
    if (!api) return
    setSettingsSaving(true)
    setSettingsError('')
    try {
      const response = await api.save_settings(values)
      if (!response.ok) throw new Error(response.error)
      setSettingsConfig(response.settings)
      applyWeatherSettings(response.settings)
      setWeatherRevision((current) => current + 1)
      setState(null)
      const connectedState = await callApi('connect')
      if (connectedState) {
        setSettingsOpen(false)
      } else {
        setSettingsError('Settings were saved, but the AC did not connect. Check the values and try again.')
      }
    } catch (error) {
      setSettingsError(error?.message || String(error))
    } finally {
      setSettingsSaving(false)
    }
  }, [applyWeatherSettings, callApi])

  useEffect(() => {
    const start = async () => {
      await readSettings()
      const connectedState = await callApi('connect')
      if (!connectedState) {
        setSettingsError('Enter the account used to pair the AC, then save and connect.')
        setSettingsOpen(true)
      }
    }
    if (window.pywebview?.api) start()
    else window.addEventListener('pywebviewready', start, { once: true })
    return () => window.removeEventListener('pywebviewready', start)
  }, [callApi, readSettings])

  useEffect(() => {
    if (!state) return undefined
    const timer = window.setInterval(async () => {
      if (busy || backgroundRefreshRef.current || commandLoopRef.current) return
      backgroundRefreshRef.current = true
      try {
        await callApi('refresh', undefined, { silent: true })
      } finally {
        backgroundRefreshRef.current = false
      }
    }, 15000)
    return () => window.clearInterval(timer)
  }, [busy, callApi, state])

  useEffect(() => {
    if (!weatherSettingsReady) return undefined
    refreshWeather()
    const weatherTimer = window.setInterval(refreshWeather, WEATHER_REFRESH_MS)
    return () => window.clearInterval(weatherTimer)
  }, [refreshWeather, weatherRevision, weatherSettingsReady])

  const refreshAll = useCallback(async () => {
    // The two requests are independent: weather trouble must never prevent
    // the AC from refreshing (and an AC error must not cancel the weather).
    const weatherRequest = refreshWeather()
    await callApi(state ? 'refresh' : 'connect')
    await weatherRequest
  }, [callApi, refreshWeather, state])

  const flushChanges = useCallback(async () => {
    if (commandLoopRef.current) return
    commandLoopRef.current = true
    let needsRecoveryRefresh = false
    try {
      while (Object.keys(queuedChangesRef.current).length > 0) {
        const changes = queuedChangesRef.current
        queuedChangesRef.current = {}
        const confirmed = await callApi('apply', changes, {
          silent: true,
          commitState: false,
        })
        if (confirmed) {
          // Preserve any newer choices made while this command was in flight.
          setState(withOptimisticChanges(confirmed, queuedChangesRef.current))
        } else {
          needsRecoveryRefresh = true
        }
      }
      if (needsRecoveryRefresh) {
        await callApi('refresh', undefined, { silent: true })
      }
    } finally {
      commandLoopRef.current = false
    }
  }, [callApi])

  const apply = useCallback((changes) => {
    setState((current) => withOptimisticChanges(current, changes))
    queuedChangesRef.current = { ...queuedChangesRef.current, ...changes }
    void flushChanges()
  }, [flushChanges])
  const supportedFeatures = useMemo(() => new Set(state?.supported_features ?? []), [state])
  const connected = Boolean(state)

  const temperatureText = state?.indoor_temperature == null
    ? '—'
    : `${state.indoor_temperature.toFixed(1)}°C`
  const outdoorText = state?.outdoor_temperature == null
    ? '—'
    : `${state.outdoor_temperature.toFixed(1)}°C`
  const modeTheme = !state
    ? 'cool'
    : !state.power
      ? 'off'
      : {
          COOL: 'cool',
          HEAT: 'heat',
          DRY: 'dry',
          FAN_ONLY: 'fan',
        }[state.mode] ?? 'cool'

  useEffect(() => {
    document.title = state?.device_name
      ? `${state.device_name} · AirCon Control`
      : 'AirCon Control'
  }, [state?.device_name])

  return (
    <main className={`app mode-${modeTheme}`}>
      <section className="blue-surface">
        <header className="topbar">
          <button className="settings-button" onClick={openSettings} aria-label="Open device settings" title="Device settings">
            <UiIcon icon={Settings} size={20} />
          </button>
          <div className="topbar__title">
            <h1>{state?.device_name || 'AirCon Control'}</h1>
            <button
              className="connection__toggle"
              onClick={() => setConnectionOpen((open) => !open)}
              aria-expanded={connectionOpen}
              aria-controls="connection-details"
              aria-label={`${connectionOpen ? 'Hide' : 'Show'} connection details. ${status}`}
              title={`${connectionOpen ? 'Hide' : 'Show'} connection details`}
            >
              <UiIcon icon={connectionOpen ? ChevronUp : ChevronDown} size={15} />
            </button>
          </div>
          <button
            className="refresh"
            disabled={busy}
            onClick={refreshAll}
            title="Refresh AC status and weather"
            aria-label="Refresh AC status and weather"
          >
            <UiIcon icon={RefreshCw} size={21} />
          </button>
        </header>

        <div className="connection">
          <div
            id="connection-details"
            className={`connection__panel ${connectionOpen ? 'is-open' : ''}`}
            aria-hidden={!connectionOpen}
          >
            <div className="connection__panel-inner">
              <div className="connection__model">
                {state?.model_number || 'Midea-compatible air conditioner'}
              </div>
              <div className="connection__title">
                <span className={`status-dot ${connected ? 'online' : ''}`} />
                {status}
              </div>
              <div className="connection__detail">{detail}</div>
            </div>
          </div>
        </div>

        <div className="climate-summary">
          <div
            className="climate-reading"
            title="Indoor temperature"
            aria-label={`Indoor temperature ${temperatureText}`}
          >
            <UiIcon icon={House} size={17} />
            <span>{temperatureText}</span>
          </div>
          <div
            className="climate-reading"
            title={`Outdoor temperature · ${weather.label}`}
            aria-label={`Outdoor temperature ${outdoorText}, ${weather.label}`}
          >
            <UiIcon icon={weather.icon} size={18} />
            <span>{outdoorText}</span>
          </div>
        </div>

        <nav className="mode-row" aria-label="Operating mode">
          {MODES.map((mode) => (
            <button
              key={mode.value}
              className={state?.mode === mode.value ? 'selected' : ''}
              disabled={busy || !state?.supported_modes?.includes(mode.value)}
              onClick={() => apply({ mode: mode.label })}
            >
              <UiIcon icon={mode.icon} size={21} />
              {mode.label === 'Fan Only' ? 'Fan' : mode.label}
            </button>
          ))}
        </nav>

        <TemperatureDial state={state} disabled={!connected || busy} onCommit={(temperature) => apply({ temperature })} />

        <button
          className={`power ${state?.power ? 'is-on' : ''}`}
          disabled={!connected || busy}
          onClick={() => apply({ power: !state.power })}
          aria-label={state?.power ? 'Turn AC off' : 'Turn AC on'}
        >
          <UiIcon icon={Power} size={29} />
        </button>
      </section>

      {sheetOpen && (
        <button
          className="sheet-backdrop"
          onClick={() => {
            setDetailsOpen(false)
            setSheetOpen(false)
          }}
          aria-label="Close controls"
        />
      )}

      <section className={`bottom-sheet ${sheetOpen ? 'is-open' : ''}`}>
        <button
          className="sheet-handle"
          onClick={() => {
            if (sheetOpen) setDetailsOpen(false)
            setSheetOpen((open) => !open)
          }}
          aria-label={sheetOpen ? 'Close controls' : 'Open controls'}
        >
          <span />
        </button>

        {!sheetOpen && (
          <div className="sheet-shortcuts">
            <button onClick={() => setSheetOpen(true)}>
              <UiIcon icon={Wind} className="feature-icon" />
              <span>Fan speed</span>
            </button>
            {FEATURES.slice(0, 3).map((feature) => (
              <button
                key={feature.key}
                className={state?.[feature.key] ? 'active' : ''}
                disabled={busy || !supportedFeatures.has(feature.key)}
                onClick={() => apply({ [feature.key]: !state[feature.key] })}
              >
                <UiIcon icon={feature.icon} className="feature-icon" />
                <span>{feature.label}</span>
              </button>
            ))}
          </div>
        )}

        {sheetOpen && (
          <div className="sheet-content">
            <h2>Fan speed</h2>
            <div className="segmented">
              {FAN_SPEEDS.map((fan) => (
                <button
                  key={fan.value}
                  className={state?.fan_speed === fan.value ? 'active' : ''}
                  disabled={busy || !state?.supported_fan_speeds?.includes(fan.value)}
                  onClick={() => apply({ fan_speed: fan.label })}
                >
                  {fan.label}
                </button>
              ))}
            </div>

            <h2>Quick controls</h2>
            <div className="feature-grid">
              {FEATURES.slice(0, 6).map((feature) => (
                <button
                  key={feature.key}
                  className={state?.[feature.key] ? 'active' : ''}
                  disabled={busy || !supportedFeatures.has(feature.key)}
                  onClick={() => apply({ [feature.key]: !state[feature.key] })}
                >
                  <UiIcon icon={feature.icon} size={17} className="feature-icon" />
                  <span>{feature.label}</span>
                </button>
              ))}
            </div>

            <button className="details-toggle" onClick={() => setDetailsOpen((open) => !open)}>
              <UiIcon icon={detailsOpen ? ChevronUp : ChevronDown} size={14} />
              {detailsOpen ? 'Hide details' : 'Show details and more controls'}
            </button>

            {detailsOpen && (
              <div className="details">
                <div className="telemetry">
                  <div><span>Power</span><b>{state?.real_time_power == null ? '—' : `${state.real_time_power.toFixed(0)} W`}</b></div>
                  <div><span>Total energy</span><b>{state?.total_energy == null ? '—' : `${state.total_energy.toFixed(2)} kWh`}</b></div>
                  <div><span>Filter</span><b>{state?.filter_alert ? 'Clean' : 'OK'}</b></div>
                  <div><span>System</span><b>{state?.error_code ? `Error ${state.error_code}` : 'OK'}</b></div>
                </div>
                <div className="secondary-grid">
                  {FEATURES.slice(6).map((feature) => (
                    <button
                      key={feature.key}
                      className={state?.[feature.key] ? 'active' : ''}
                      disabled={busy || !supportedFeatures.has(feature.key)}
                      onClick={() => apply({ [feature.key]: !state[feature.key] })}
                    >
                      <UiIcon icon={feature.icon} size={14} /> {feature.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {settingsOpen && settingsConfig && (
        <SettingsDialog
          initial={settingsConfig}
          saving={settingsSaving}
          error={settingsError}
          onClose={() => setSettingsOpen(false)}
          onSave={saveSettings}
        />
      )}
    </main>
  )
}

export default App
