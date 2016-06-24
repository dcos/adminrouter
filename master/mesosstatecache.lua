local cjson_safe = require "cjson.safe"
local shmlock = require "resty.lock"
local http = require "resty.http.simple"


local _M = {}


local POLL_PERIOD_SECONDS = 25
local CACHE_EXPIRATION_SECONDS = 20


local function cache_data(key, value)
    -- Store key/value pair to SHM cache (shared across workers).
    -- Return true upon success, false otherwise.
    -- Expected to run within lock context.

    local cache = ngx.shared.mesos_state_cache
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


local function request(host, port, path)
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
        return nil, "invalid response status: " .. res.status
    end

    ngx.log(
        ngx.NOTICE,
        "Request host: " .. host .. ", port: " .. port .. ", path: " .. path .. ". " ..
        "Response Body length: " .. string.len(res.body) .. " bytes."
        )

    return res, nil
end


local function fetch_and_cache_state_marathon()
    -- Access Marathon through localhost.
    ngx.log(ngx.NOTICE, "Cache Marathon app state")
    local appsRes, err = request("127.0.0.1", 8080, "/v2/apps?embed=apps.tasks&label=DCOS_SERVICE_NAME")

    if err then
        ngx.log(ngx.NOTICE, "Marathon app request failed: " .. err)
        return
    end

    local apps, err = cjson_safe.decode(appsRes.body)
    if not apps then
        ngx.log(ngx.NOTICE, "Cannot decode Marathon apps JSON: " .. err)
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
       if not tasks then
          ngx.log(ngx.NOTICE, "Cannot find tasks for app '" .. appId .. "'")
          return
       end

       local _, task = next(tasks)
       if not task then
          ngx.log(ngx.NOTICE, "Cannot find any task for app '" .. appId .. "'")
          goto continue
       end

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

    svcApps = cjson_safe.encode(svcApps)
    ngx.log(ngx.DEBUG, "storing services " .. svcApps)

    ngx.update_time()
    local time_fetched = ngx.now()
    ngx.log(ngx.DEBUG, "Storing Marathon state to SHM.")

    local success = cache_data("svcapps", svcApps)
    if success then
        cache_data("last_fetch_time_marathon", time_fetched)
    end
end


local function fetch_and_cache_state_mesos()
    -- Fetch state JSON summary from Mesos. If successful, store to SHM cache.
    -- Expected to run within lock context.
    local mesosRes, err = request("leader.mesos", 5050, "/master/state-summary")

    if err then
        ngx.log(ngx.NOTICE, "Mesos state request failed: " .. err)
        return
    end

    ngx.update_time()
    local time_fetched = ngx.now()
    ngx.log(ngx.DEBUG, "Storing Mesos state to SHM.")

    local success = cache_data("statejson", mesosRes.body)
    if success then
        cache_data("last_fetch_time_mesos", time_fetched)
    end

    -- Piggy-back this and attempt to update the Marathon service
    -- cache, too. TODO(jp): decouple these entirely, so that the
    -- Marathon app cache can get its own timing/execution logic.
    fetch_and_cache_state_marathon()
end


local function refresh_mesos_state_cache(from_timer)
    -- Refresh state cache if not yet existing or if expired.
    -- Use SHM-based lock for synchronizing coroutines
    -- across worker processes.
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
        -- Fail immediately if another worker currently holds
        -- the lock, because a single timer-based update at any
        -- given time suffices.
        lock = shmlock:new("shmlocks", { timeout=0 })
        local elapsed, err = lock:lock("mesos-state")
        if elapsed == nil then
            ngx.log(ngx.DEBUG, "Concurrent timer performs update. Noop.")
            return
        end
    else
        -- Cache content is required for current request
        -- processing. Wait for lock acquisition, for at
        -- most 20 seconds.
        lock = shmlock:new("shmlocks", { timeout=20 })
        local elapsed, err = lock:lock("mesos-state")
        if elapsed == nil then
            ngx.log(ngx.ERR, "Could not acquire lock: " .. err)
            -- Leave early (did not make sure that cache is populated).
            return
        end
    end
    local cache = ngx.shared.mesos_state_cache

    -- Handle special case of first invocation.
    local fetchtime = cache:get("last_fetch_time_mesos")
    if not fetchtime then
        ngx.log(ngx.NOTICE, "Cache empty. Fetch.")
        fetch_and_cache_state_mesos()
    else
        ngx.update_time()
        local diff = ngx.now() - fetchtime
        if diff > CACHE_EXPIRATION_SECONDS then
            ngx.log(ngx.NOTICE, "Mesos state cache expired. Refresh.")
            fetch_and_cache_state_mesos()
        else
            ngx.log(ngx.DEBUG, "Cache populated and not expired. Noop.")
        end
    end

    local ok, err = lock:unlock()
    if not ok then
        -- If this fails, an unlock happens automatically,
        -- by default after 30 seconds, to prevent deadlock.
        ngx.log(
            ngx.ERR,
            "Failed to unlock mesos-state shmlock: " .. err
            )
    end
end


function _M.periodically_poll_mesos_state()
    -- This function is invoked from within init_worker_by_lua code.
    -- ngx.timer.at() can be called here, whereas most of the other ngx.*
    -- API is not availabe.

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
        refresh_mesos_state_cache(true)

        -- Register new timer.
        local ok, err = ngx.timer.at(POLL_PERIOD_SECONDS, timerhandler)
        if not ok then
            ngx.log(ngx.ERR, "Failed to create timer: " .. err)
        end
    end

    -- Trigger initial timer, about 2 seconds after nginx startup.
    local ok, err = ngx.timer.at(2, timerhandler)
    if not ok then
        ngx.log(ngx.ERR, "failed to create timer: " .. err)
        return
    end
    ngx.log(ngx.DEBUG, "Created recursive timer for Mesos state polling.")
end


local function get_svcapps(retry)
   local cache = ngx.shared.mesos_state_cache
   local svcappsjson = cache:get("svcapps")
   if not svcappsjson then
        if retry then
            ngx.log(
                ngx.ERR,
                "Could not retrieve Service state when first requested."
            )
            return nil
        end
        ngx.log(
            ngx.NOTICE,
            "Service state not available in cache yet. Fetch it."
        )
        refresh_mesos_state_cache()
        return get_svcapps(true)
    end
    return svcappsjson
end


-- Expose interface for requesting service summary JSON.
_M.get_svcapps = get_svcapps


local function get_state_summary(retry)
    -- Fetch state summary JSON from cache and handle
    -- special case of cache not yet existing.
    local cache = ngx.shared.mesos_state_cache
    local statejson = cache:get("statejson")
    if not statejson then
        if retry then
            ngx.log(
                ngx.ERR,
                "Coud not retrieve Mesos state when first requested."
            )
            return nil
        end
        ngx.log(
            ngx.NOTICE,
            "Mesos state not available in cache yet. Fetch it."
        )
        refresh_mesos_state_cache()
        return get_state_summary(true)
    end
    return statejson
end


-- Expose interface for requesting state summary JSON.
_M.get_state_summary = get_state_summary


return _M
