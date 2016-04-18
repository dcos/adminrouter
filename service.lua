local common = require "common"
local url = require "url"

function gen_serviceurl(service_name)
    local records = common.mesos_dns_get_srv(service_name)
    local first_ip = records[1]['ip']
    local first_port = records[1]['port']
    ngx.var.servicescheme = "http"
    return "http://" .. first_ip .. ":" .. first_port
end

-- Get (cached) Marathon app state.
local svcapps = common.get_svcapps()
if svcapps then
    local svc = svcapps[ngx.var.serviceid]
    if svc then
       ngx.var.serviceurl = svc["url"]
       ngx.var.servicescheme = svc["scheme"]
       return
    end
end

-- Get (cached) Mesos state.
local state = common.mesos_get_state()
for _, framework in ipairs(state["frameworks"]) do
    if framework["id"] == ngx.var.serviceid or framework['name'] == ngx.var.serviceid then
        local split_pid = framework["pid"]:split("@")
        local split_ipport = split_pid[2]:split(":")
        local host = split_ipport[1]
        local webui_url = framework["webui_url"]
        if webui_url == "" then
            ngx.var.serviceurl = gen_serviceurl(framework['name'])
            return
        else
            local parsed_webui_url = url.parse(webui_url)
            parsed_webui_url.host = host
            if parsed_webui_url.path == "/" then
                parsed_webui_url.path = ""
            end
            ngx.var.serviceurl = parsed_webui_url:build()
            ngx.var.servicescheme = parsed_webui_url.scheme
            return
        end
        ngx.log(ngx.DEBUG, ngx.var.serviceurl)
    end
end
