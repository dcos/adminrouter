local cjson_safe = require "cjson.safe"
local statecache = require "master.mesosstatecache"

local util = {}


function util.mesos_dns_get_srv(framework_name)
    local res = ngx.location.capture(
        "/mesos_dns/v1/services/_" .. framework_name .. "._tcp.marathon.mesos")

    if res.truncated then
        -- Remote connection dropped prematurely or timed out.
        ngx.log(ngx.ERR, "Request to Mesos DNS failed.")
        return nil
    end
    if res.status ~= 200 then
        ngx.log(ngx.ERR, "Mesos DNS response status: " .. res.status)
        return nil
    end

    local records, err = cjson_safe.decode(res.body)
    if not records then
        ngx.log(ngx.ERR, "Cannot decode JSON: " .. err)
        return nil
    end
    return records
end


function util.get_svcapps()
    -- Read Mesos state JSON from SHM cache.
    -- Return decoded JSON or nil upon error.
    local appsjson = statecache.get_svcapps()
    local apps, err = cjson_safe.decode(appsjson)
    if not apps then
        ngx.log(ngx.ERR, "Cannot decode JSON: " .. err)
        return nil
    end
    return apps
end


function util.mesos_get_state()
    -- Read Mesos state JSON from SHM cache.
    -- Return decoded JSON or nil upon error.
    local statejson = statecache.get_state_summary()
    local state, err = cjson_safe.decode(statejson)
    if not state then
        ngx.log(ngx.ERR, "Cannot decode JSON: " .. err)
        return nil
    end
    return state
end


return util
