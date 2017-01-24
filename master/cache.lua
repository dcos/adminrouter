local cjson_safe = require "cjson.safe"
local shmlock = require "resty.lock"
local http = require "resty.http.simple"


local _M = {}

-- In order to make caching code testable, these constants need to be
-- configurable/exposed through env vars.
--
-- Values assigned to these variable need to fufil following condidtion:
--
-- CACHE_FIRST_POLL_DELAY_SECONDS << CACHE_EXPIRATION_SECONDS < CACHE_POLL_PERIOD_SECONDS
--
--
local CACHE_FIRST_POLL_DELAY_SECONDS = os.getenv("CACHE_FIRST_POLL_DELAY_SECONDS")
if CACHE_FIRST_POLL_DELAY_SECONDS == nil then
    CACHE_FIRST_POLL_DELAY_SECONDS = 2
    ngx.log(ngx.DEBUG, "CACHE_FIRST_POLL_DELAY_SECONDS not set by ENV, using default")
else
    CACHE_FIRST_POLL_DELAY_SECONDS = tonumber(CACHE_FIRST_POLL_DELAY_SECONDS)
    ngx.log(ngx.WARN,
            "CACHE_FIRST_POLL_DELAY_SECONDS has been overridden by ENV to `" .. CACHE_FIRST_POLL_DELAY_SECONDS .. "`")
end

local CACHE_POLL_PERIOD_SECONDS = os.getenv("CACHE_POLL_PERIOD_SECONDS")
if CACHE_POLL_PERIOD_SECONDS == nil then
    CACHE_POLL_PERIOD_SECONDS = 25
    ngx.log(ngx.DEBUG, "CACHE_POLL_PERIOD_SECONDS not set by ENV, using default")
else
    CACHE_POLL_PERIOD_SECONDS = tonumber(CACHE_POLL_PERIOD_SECONDS)
    ngx.log(ngx.WARN,
            "CACHE_POLL_PERIOD_SECONDS has been overridden by ENV to `" .. CACHE_POLL_PERIOD_SECONDS .. "`")
end

local CACHE_EXPIRATION_SECONDS = os.getenv("CACHE_EXPIRATION_SECONDS")
if CACHE_EXPIRATION_SECONDS == nil then
    CACHE_EXPIRATION_SECONDS = 20
    ngx.log(ngx.DEBUG, "CACHE_EXPIRATION_SECONDS not set by ENV, using default")
else
    CACHE_EXPIRATION_SECONDS = tonumber(CACHE_EXPIRATION_SECONDS)
    ngx.log(ngx.WARN,
            "CACHE_EXPIRATION_SECONDS has been overridden by ENV to `" .. CACHE_EXPIRATION_SECONDS .. "`")
end


local function cache_data(key, value)
    -- Store key/value pair to SHM cache (shared across workers).
    -- Return true upon success, false otherwise.
    -- Expected to run within lock context.

    local cache = ngx.shared.cache
    local success, err, forcible = cache:set(key, value)
    if success then
        return true
    end
    ngx.log(
        ngx.ERR,
        "Could not store " .. key .. " to state cache: " .. err
        )
    return false
end


local function request(host, port, path, accept_404_reply)
    -- Use cosocket-based HTTP library, as ngx subrequests are not available
    -- from within this code path (decoupled from nginx' request processing).
    -- The timeout parameter is given in milliseconds.
    local res, err = http.request(host, port,
        {
            path = path,
            timeout = 10000,
        }
    )

    if not res then
        return nil, err
    end

    if res.status ~= 200 then
        if accept_404_reply and res.status ~= 404 or not accept_404_reply then
            return nil, "invalid response status: " .. res.status
        end
    end

    ngx.log(
        ngx.NOTICE,
        "Request host: " .. host .. ", port: " .. port .. ", path: " .. path .. ". " ..
        "Response Body length: " .. string.len(res.body) .. " bytes."
        )

    return res, nil
end


local function fetch_and_store_marathon_apps()
    -- Access Marathon through localhost.
    ngx.log(ngx.NOTICE, "Cache Marathon app state")
    local appsRes, err = request("127.0.0.1", 8080,
                                 "/v2/apps?embed=apps.tasks&label=DCOS_SERVICE_NAME",
                                 false)

    if err then
        ngx.log(ngx.NOTICE, "Marathon app request failed: " .. err)
        if not cache_data("svcapps", nil) then
            ngx.log(ngx.ERR, "Invalidating Marathon apps cache failed")
        end
        return
    end

    local apps, err = cjson_safe.decode(appsRes.body)
    if not apps then
        ngx.log(ngx.NOTICE, "Cannot decode Marathon apps JSON: " .. err)
        if not cache_data("svcapps", nil) then
            ngx.log(ngx.ERR, "Invalidating Marathon apps cache failed")
        end
        return
    end

    local svcApps = {}
    for _, app in ipairs(apps["apps"]) do
       local appId = app["id"]
       local labels = app["labels"]
       if not labels then
          ngx.log(ngx.NOTICE, "Labels not found in app '" .. appId .. "': " .. err)
          goto continue
       end

       -- Service name should exist as we asked Marathon for it
       local svcId = labels["DCOS_SERVICE_NAME"]

       local scheme = labels["DCOS_SERVICE_SCHEME"]
       if not scheme then
          ngx.log(ngx.NOTICE, "Cannot find DCOS_SERVICE_SCHEME for app '" .. appId .. "'")
          goto continue
       end

       local portIdx = labels["DCOS_SERVICE_PORT_INDEX"]
       if not portIdx then
          ngx.log(ngx.NOTICE, "Cannot find DCOS_SERVICE_PORT_INDEX for app '" .. appId .. "'")
          goto continue
       end

       -- Lua arrays default starting index is 1 not the 0 of marathon
       local portIdx = tonumber(portIdx) + 1
       if not portIdx then
          ngx.log(ngx.NOTICE, "Cannot convert port to number for app '" .. appId .. "'")
          goto continue
       end

       local tasks = app["tasks"]

       -- Process only tasks in TASK_RUNNING state.
       -- From http://lua-users.org/wiki/TablesTutorial: "inside a pairs loop,
       -- it's safe to reassign existing keys or remove them"
       for i, t in ipairs(tasks) do
          if t["state"] ~= "TASK_RUNNING" then
             table.remove(tasks, i)
          end
       end

       -- next() returns nil if table is empty.
       local i, task = next(tasks)
       if i == nil then
          ngx.log(ngx.NOTICE, "No task in state TASK_RUNNING for app '" .. appId .. "'")
          goto continue
       end

       ngx.log(
          ngx.NOTICE,
          "Reading state for appId '" .. appId .. "' from task with id '" .. task["id"] .. "'"
          )

       local host = task["host"]
       if not host then
          ngx.log(ngx.NOTICE, "Cannot find host for app '" .. appId .. "'")
          goto continue
       end

       local ports = task["ports"]
       if not ports then
          ngx.log(ngx.NOTICE, "Cannot find ports for app '" .. appId .. "'")
          goto continue
       end

       local port = ports[portIdx]
       if not port then
          ngx.log(ngx.NOTICE, "Cannot find port at port index '" .. portIdx .. "' for app '" .. appId .. "'")
          goto continue
       end

       local url = scheme .. "://" .. host .. ":" .. port
       svcApps[svcId] = {scheme=scheme, url=url}

       ::continue::
    end

    svcApps_json = cjson_safe.encode(svcApps)

    ngx.log(ngx.DEBUG, "Storing Marathon services data to SHM.")
    if not cache_data("svcapps", svcApps_json) then
        ngx.log(ngx.ERR, "Storing marathon apps cache failed")
        return
    end

    ngx.update_time()
    local time_now = ngx.now()
    if cache_data("svcapps_last_refresh", time_now) then
        ngx.log(ngx.INFO, "Marathon apps cache has been successfully updated")
    end

    return
end


local function fetch_and_store_marathon_leader()
    -- Fetch Marathon leader address. If successful, store to SHM cache.
    -- Expected to run within lock context.
    local mleaderRes, err = request("127.0.0.1", 8080, "/v2/leader", true)

    if err then
        ngx.log(ngx.NOTICE, "Marathon leader request failed: " .. err)
        if not cache_data("marathonleader", nil) then
            ngx.log(ngx.ERR, "Invalidating Marathon leader cache failed")
        end
        return
    end

    -- https://mesosphere.github.io/marathon/docs/rest-api.html#get-v2-leader
    if mleaderRes.status == 404 then
        ngx.log(ngx.NOTICE, "Storing empty Marathon leader to SHM")
        local empty_leader_json = '{"port": 0, "address": "not elected"}'
        if not cache_data("marathonleader", empty_leader_json) then
            ngx.log(ngx.ERR, "Storing Marathon leader cache failed")
        end
        return
    end

    local mleader, err = cjson_safe.decode(mleaderRes.body)
    if not mleader then
        ngx.log(ngx.NOTICE, "Cannot decode Marathon leader JSON: " .. err)
        if not cache_data("marathonleader", nil) then
            ngx.log(ngx.ERR, "Invalidating Marathon leader cache failed")
        end
        return
    end

    local split_mleader = mleader['leader']:split(":")
    local parsed_mleader = {}
    parsed_mleader["address"] = split_mleader[1]
    parsed_mleader["port"] = split_mleader[2]
    local mleader = cjson_safe.encode(parsed_mleader)

    ngx.log(ngx.DEBUG, "Storing Marathon leader to SHM")
    if not cache_data("marathonleader", mleader) then
        ngx.log(ngx.ERR, "Storing Marathon leader cache failed")
        return
    end

    ngx.update_time()
    local time_now = ngx.now()
    if cache_data("marathonleader_last_refresh", time_now) then
        ngx.log(ngx.INFO, "Marathon leader cache has been successfully updated")
    end

    return
end


local function fetch_and_store_state_mesos()
    -- Fetch state JSON summary from Mesos. If successful, store to SHM cache.
    -- Expected to run within lock context.
    local mesosRes, err = request("leader.mesos", 5050, "/master/state-summary", false)

    if err then
        ngx.log(ngx.NOTICE, "Mesos state request failed: " .. err)
        if not cache_data("mesosstate", nil) then
            ngx.log(ngx.ERR, "Invalidating Mesos state cache failed")
        end
        return
    end

    ngx.log(ngx.DEBUG, "Storing Mesos state to SHM.")
    if not cache_data("mesosstate", mesosRes.body) then
        ngx.log(ngx.ERR, "Storing mesos state cache failed")
        return
    end

    ngx.update_time()
    local time_now = ngx.now()
    if cache_data("mesosstate_last_refresh", time_now) then
        ngx.log(ngx.INFO, "Mesos state cache has been successfully updated")
    end

    return
end


local function refresh_needed(ts_name)
    local cache = ngx.shared.cache

    local last_fetch_time = cache:get(ts_name)
    -- Handle special case of first invocation.
    if not last_fetch_time then
        ngx.log(ngx.INFO, "Cache `".. ts_name .. "` empty. Fetching.")
        return true
    else
        ngx.update_time()
        local diff = ngx.now() - last_fetch_time
        if diff > CACHE_EXPIRATION_SECONDS then
            ngx.log(ngx.INFO, "Cache `".. ts_name .. "` expired. Refresh.")
            return true
        else
            ngx.log(ngx.DEBUG, "Cache `".. ts_name .. "` populated and fresh. NOOP.")
        end
    end

    return false
end


local function refresh_cache(from_timer)
    -- Refresh cache in case when it expired or has not been created yet.
    -- Use SHM-based lock for synchronizing coroutines across worker processes.
    --
    -- This function can be invoked via two mechanisms:
    --
    --  * Via ngx.timer (in a coroutine), which is triggered
    --    periodically in all worker processes for performing an
    --    out-of-band cache refresh (this is the usual mode of operation).
    --    In that case, perform cache invalidation only if no other timer
    --    instance currently does so (abort if lock cannot immediately be
    --    acquired).
    --
    --  * During HTTP request processing, when cache content is
    --    required for answering the request but the cache was not
    --    populated yet (i.e. usually early after nginx startup).
    --    In that case, return from this function only after the cache
    --    has been populated (block on lock acquisition).
    --
    -- Args:
    --      from_timer: set to true if invoked from a timer

    -- Acquire lock.
    local lock
    if from_timer then
        ngx.log(ngx.INFO, "Executing cache refresh triggered by timer")
        -- Fail immediately if another worker currently holds
        -- the lock, because a single timer-based update at any
        -- given time suffices.
        lock = shmlock:new("shmlocks", { timeout=0 })
        local elapsed, err = lock:lock("cache")
        if elapsed == nil then
            ngx.log(ngx.INFO, "Timer-based update is in progress. NOOP.")
            return
        end
    else
        ngx.log(ngx.INFO, "Executing cache refresh triggered by request")
        -- Cache content is required for current request
        -- processing. Wait for lock acquisition, for at
        -- most 20 seconds.
        lock = shmlock:new("shmlocks", { timeout=20 })
        local elapsed, err = lock:lock("cache")
        if elapsed == nil then
            ngx.log(ngx.ERR, "Could not acquire lock: " .. err)
            -- Leave early (did not make sure that cache is populated).
            return
        end
    end

    if refresh_needed("mesosstate_last_refresh") then
        fetch_and_store_state_mesos()
    end

    if refresh_needed("svcapps_last_refresh") then
        fetch_and_store_marathon_apps()
    end

    if refresh_needed("marathonleader_last_refresh") then
        fetch_and_store_marathon_leader()
    end

    local ok, err = lock:unlock()
    if not ok then
        -- If this fails, an unlock happens automatically,
        -- by default after 30 seconds, to prevent deadlock.
        ngx.log(ngx.ERR, "Failed to unlock cache shmlock: " .. err)
    end
end


function _M.periodically_refresh_cache()
    -- This function is invoked from within init_worker_by_lua code.
    -- ngx.timer.at() can be called here, whereas most of the other ngx.*
    -- API is not available.

    timerhandler = function(premature)
        -- Handler for recursive timer invocation.
        -- Within a timer callback, plenty of the ngx.* API is available,
        -- with the exception of e.g. subrequests. As ngx.sleep is also not
        -- available in the current context, the recommended approach of
        -- implementing periodic tasks is via recursively defined timers.

        -- Premature timer execution: worker process tries to shut down.
        if premature then
            return
        end

        -- Invoke timer business logic.
        refresh_cache(true)

        -- Register new timer.
        local ok, err = ngx.timer.at(CACHE_POLL_PERIOD_SECONDS, timerhandler)
        if not ok then
            ngx.log(ngx.ERR, "Failed to create timer: " .. err)
        else
            ngx.log(ngx.INFO, "Created recursive timer for cache updating.")
        end
    end

    -- Trigger initial timer, about CACHE_FIRST_POLL_DELAY_SECONDS seconds after
    -- nginx startup.
    local ok, err = ngx.timer.at(CACHE_FIRST_POLL_DELAY_SECONDS, timerhandler)
    if not ok then
        ngx.log(ngx.ERR, "failed to create timer: " .. err)
        return
    else
        ngx.log(ngx.INFO, "Created initial recursive timer for cache updating.")
    end
end


function _M.get_cache_entry(name)
    local cache = ngx.shared.cache
    if refresh_needed(name .. "_last_refresh") then
        refresh_cache()
    end

    local entry_json = cache:get(name)
    if entry_json == nil then
        ngx.log(ngx.ERR, "Could not retrieve `" .. name .. "` cache entry")
        return nil
    end

    local entry, err = cjson_safe.decode(entry_json)
    if entry == nil then
        ngx.log(ngx.ERR, "Cannot decode JSON for entry `" .. entry_json .. "`: " .. err)
        return nil
    end

    return entry
end


return _M
