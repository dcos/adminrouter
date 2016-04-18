ngx.header.content_type = 'application/json'

local public_ip = os.getenv('COREOS_PUBLIC_IPV4')

if not public_ip then
    public_ip = ngx.var.server_addr
end

local cluster_id = io.open('/var/lib/dcos/cluster-id', 'r')

if cluster_id == nil
then
    ngx.say('{"PUBLIC_IPV4": "' .. public_ip .. '"}')
else
    ngx.say('{"PUBLIC_IPV4": "' .. public_ip .. '", "CLUSTER_ID": "' .. cluster_id:read() .. '"}')
end
