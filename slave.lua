local common = require "common"

local state = common.mesos_get_state()
if state == nil then
    ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
    ngx.say("503 Service Unavailable: invalid Mesos state.")
    return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
end
for _, slave in ipairs(state["slaves"]) do
    if slave["id"] == ngx.var.slaveid then
        local split_pid = slave["pid"]:split("@")
        ngx.var.slaveaddr = split_pid[2]
        ngx.log(
            ngx.DEBUG, "slaveid / slaveaddr:" .. 
            ngx.var.slaveid .. " / " .. ngx.var.slaveaddr
            )
        return
    end
end
ngx.status = ngx.HTTP_NOT_FOUND
ngx.say("404 Not Found: slave " .. ngx.var.slaveid .. " unknown.")
return ngx.exit(ngx.HTTP_NOT_FOUND) 
