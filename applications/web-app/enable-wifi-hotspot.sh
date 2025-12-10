#!/bin/sh -
# Copyright (C) 2018, STMicroelectronics - All Rights Reserved

#
# Wi-Fi Hotspot Script with mDNS Support (for STM32MP257)
# Disconnects from Wi-Fi and creates a hotspot on wlan0
# Access via: http://<hostname>.local:8000
#
# For changing the password and SSID:
# cat > /etc/default/hostapd << EOF
# HOSTAPD_SSID=YourNetworkName
# HOSTAPD_PASSWD=YourPassword
# EOF


if [ -f /etc/default/hostapd ]; then
    . /etc/default/hostapd
else
    HOSTAPD_SSID=RBT01Demo
    HOSTAPD_PASSWD=12345678
fi

# Export for use by calling scripts
export HOSTAPD_SSID
export HOSTAPD_PASSWD

# Interface to use for hotspot
WLAN_INTERFACE="wlan0"
# Hotspot IP address
HOTSPOT_IP="192.168.72.1"
# DHCP range
DHCP_START="192.168.72.10"
DHCP_END="192.168.72.50"
DHCP_NETMASK="255.255.255.0"
DHCP_LEASE="2m"

# Web app port
WEBAPP_PORT=8000

# Log file for debugging
LOG_FILE="/tmp/hotspot.log"

# Generated hostname (will be set dynamically)
MDNS_HOSTNAME=""

log_msg() {
    echo "$(date '+%H:%M:%S') - $1" >> $LOG_FILE
    echo "$1"
}

check_interface() {
    ip link show $WLAN_INTERFACE > /dev/null 2>&1
}

# Generate hostname from MAC address
# Format: rbt20-XX-XX-XX (last 3 octets of MAC)
generate_hostname() {
    # Get MAC address of wlan0
    MAC=$(cat /sys/class/net/$WLAN_INTERFACE/address 2>/dev/null)
    
    if [ -z "$MAC" ]; then
        # Fallback: try ip command
        MAC=$(ip link show $WLAN_INTERFACE 2>/dev/null | grep link/ether | awk '{print $2}')
    fi
    
    if [ -z "$MAC" ]; then
        # Ultimate fallback
        MDNS_HOSTNAME="rbt20-demo"
        log_msg "Could not get MAC address, using fallback hostname: $MDNS_HOSTNAME"
        return
    fi
    
    # Extract last 3 octets and format
    # MAC format: AA:BB:CC:DD:EE:FF -> rbt20-dd-ee-ff
    LAST3=$(echo "$MAC" | awk -F: '{print tolower($4"-"$5"-"$6)}')
    MDNS_HOSTNAME="rbt20-$LAST3"
    
    log_msg "Generated hostname from MAC $MAC: $MDNS_HOSTNAME"
}

# Kill all processes that might interfere
kill_interfering_processes() {
    log_msg "Stopping interfering services..."
    
    # Stop network managers
    systemctl stop wpa_supplicant 2>/dev/null
    systemctl stop NetworkManager 2>/dev/null
    
    # Kill any remaining processes
    killall wpa_supplicant 2>/dev/null
    killall hostapd 2>/dev/null
    killall dnsmasq 2>/dev/null
    
    # Wait for processes to die
    sleep 1
}

disconnect_wifi() {
    log_msg "Disconnecting from existing Wi-Fi..."
    
    kill_interfering_processes
    
    # Flush existing IP configuration
    ip addr flush dev $WLAN_INTERFACE 2>/dev/null
    
    # Bring interface down then up to reset state
    ip link set $WLAN_INTERFACE down 2>/dev/null
    sleep 1
    ip link set $WLAN_INTERFACE up 2>/dev/null
    sleep 1
    
    # Remove iptables rules if they exist
    # Remove iptables rules if they exist
    iptables -t nat -D PREROUTING -i $WLAN_INTERFACE -p tcp --dport 80 -j REDIRECT --to-port $WEBAPP_PORT 2>/dev/null || true
    
    log_msg "Wi-Fi disconnected"
}

reconnect_wifi() {
    log_msg "Restoring Wi-Fi client mode..."
    
    # Stop hotspot services
    killall hostapd 2>/dev/null
    killall dnsmasq 2>/dev/null
    
    # Stop avahi if we started it
    systemctl stop avahi-daemon 2>/dev/null
    
    # Flush IP
    ip addr flush dev $WLAN_INTERFACE 2>/dev/null
    ip link set $WLAN_INTERFACE down 2>/dev/null
    sleep 1
    ip link set $WLAN_INTERFACE up 2>/dev/null
    
    # Restart network services
    systemctl start wpa_supplicant 2>/dev/null
    systemctl start NetworkManager 2>/dev/null
    systemctl restart systemd-networkd 2>/dev/null
    
    # Restart avahi in normal mode
    systemctl start avahi-daemon 2>/dev/null
    
    log_msg "Wi-Fi client mode restored"
}

setup_interface() {
    log_msg "Setting up interface $WLAN_INTERFACE with IP $HOTSPOT_IP..."
    
    # Flush any existing addresses
    ip addr flush dev $WLAN_INTERFACE 2>/dev/null
    
    # Ensure interface is up
    ip link set $WLAN_INTERFACE up
    sleep 1
    
    # Assign static IP
    ip addr add $HOTSPOT_IP/24 dev $WLAN_INTERFACE
    
    if [ $? -ne 0 ]; then
        log_msg "ERROR: Failed to assign IP address"
        return 1
    fi
    
    # Verify IP was assigned
    ASSIGNED_IP=$(ip addr show $WLAN_INTERFACE 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1)
    if [ "$ASSIGNED_IP" != "$HOTSPOT_IP" ]; then
        log_msg "WARNING: Expected $HOTSPOT_IP but got $ASSIGNED_IP"
        return 1
    fi
    
    log_msg "IP address $HOTSPOT_IP assigned successfully"
    
    # Configure iptables to redirect port 80 to webapp port
    # This is CRITICAL for captive portal to work, as OS checks port 80
    log_msg "Setting up iptables redirect 80 -> $WEBAPP_PORT..."
    iptables -t nat -A PREROUTING -i $WLAN_INTERFACE -p tcp --dport 80 -j REDIRECT --to-port $WEBAPP_PORT || true
    
    return 0
}

create_hostapd_config() {
    log_msg "Creating hostapd configuration..."
    
    cat > /tmp/hostapd.conf << EOF
# Hostapd configuration for $WLAN_INTERFACE
interface=$WLAN_INTERFACE
driver=nl80211

# Wireless settings
ssid=$HOSTAPD_SSID
hw_mode=g
channel=7
wmm_enabled=0

# Authentication
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0

# WPA2 settings
wpa=2
wpa_passphrase=$HOSTAPD_PASSWD
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP

# Debug level (0 = minimal, 1 = debug, 2 = verbose)
logger_syslog=-1
logger_syslog_level=2
logger_stdout=-1
logger_stdout_level=2
EOF

    log_msg "Hostapd config created at /tmp/hostapd.conf"
}

create_dnsmasq_config() {
    log_msg "Creating dnsmasq configuration..."
    
    cat > /tmp/dnsmasq-hotspot.conf << EOF
# dnsmasq configuration for hotspot
interface=$WLAN_INTERFACE
bind-interfaces
dhcp-range=$DHCP_START,$DHCP_END,$DHCP_NETMASK,$DHCP_LEASE

# Set default gateway to our IP
dhcp-option=3,$HOTSPOT_IP

# DNS server
dhcp-option=6,$HOTSPOT_IP

# RFC 8908 Captive Portal API (helps modern devices detect portal)
# Note: We must implement this endpoint in main.py
dhcp-option=114,http://$HOTSPOT_IP:$WEBAPP_PORT/captive-portal-api

# Captive portal - redirect all DNS queries to our IP
address=/#/$HOTSPOT_IP

# IMPORTANT: Respond to .local queries for mDNS hostname
# This allows devices to resolve hostname.local to our IP
local=/${MDNS_HOSTNAME}.local/
address=/${MDNS_HOSTNAME}.local/$HOTSPOT_IP

# Don't use /etc/resolv.conf
no-resolv

# Log DHCP queries
log-dhcp

# PID file
pid-file=/tmp/dnsmasq-hotspot.pid
EOF

    log_msg "dnsmasq config created at /tmp/dnsmasq-hotspot.conf"
}

setup_avahi() {
    log_msg "Setting up Avahi mDNS..."
    
    # Check if avahi-daemon exists
    if ! command -v avahi-daemon > /dev/null 2>&1; then
        log_msg "WARNING: avahi-daemon not found, mDNS will not work"
        return 1
    fi
    
    # Set the system hostname temporarily
    CURRENT_HOSTNAME=$(hostname)
    hostnamectl set-hostname "$MDNS_HOSTNAME" 2>/dev/null || hostname "$MDNS_HOSTNAME"
    log_msg "Set hostname to $MDNS_HOSTNAME"
    
    # Create avahi service file for the web app
    mkdir -p /etc/avahi/services
    cat > /etc/avahi/services/webapp.service << EOF
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>X-LINUX-RBT1 Controller</name>
  <service>
    <type>_http._tcp</type>
    <port>$WEBAPP_PORT</port>
    <txt-record>path=/static/index.html</txt-record>
  </service>
</service-group>
EOF
    
    # Create avahi configuration for hotspot mode
    cat > /tmp/avahi-daemon-hotspot.conf << EOF
[server]
host-name=$MDNS_HOSTNAME
domain-name=local
use-ipv4=yes
use-ipv6=no
allow-interfaces=$WLAN_INTERFACE
deny-interfaces=eth0,eth1
ratelimit-interval-usec=1000000
ratelimit-burst=1000

[wide-area]
enable-wide-area=no

[publish]
publish-addresses=yes
publish-hinfo=yes
publish-workstation=no
publish-domain=yes
publish-dns-servers=$HOTSPOT_IP
publish-resolv-conf-dns-servers=no

[reflector]
enable-reflector=no

[rlimits]
EOF
    
    # Stop existing avahi
    systemctl stop avahi-daemon 2>/dev/null
    killall avahi-daemon 2>/dev/null
    sleep 1
    
    # Start avahi with our config
    avahi-daemon -f /tmp/avahi-daemon-hotspot.conf --no-drop-root -D 2>/dev/null
    
    if [ $? -eq 0 ]; then
        log_msg "Avahi mDNS started for $MDNS_HOSTNAME.local"
        return 0
    else
        # Try starting with default config after setting hostname
        log_msg "Trying avahi with default config..."
        systemctl start avahi-daemon 2>/dev/null
        if pgrep -x avahi-daemon > /dev/null; then
            log_msg "Avahi started with default config"
            return 0
        fi
        log_msg "WARNING: Failed to start avahi-daemon"
        return 1
    fi
}

start_hostapd() {
    log_msg "Starting hostapd..."
    
    # Kill any existing hostapd
    killall hostapd 2>/dev/null
    sleep 1
    
    # Start hostapd in background
    hostapd -B /tmp/hostapd.conf -P /tmp/hostapd.pid >> $LOG_FILE 2>&1
    
    # Wait and check if it started
    sleep 3
    
    if pgrep -x hostapd > /dev/null; then
        log_msg "hostapd started successfully"
        return 0
    else
        log_msg "ERROR: hostapd failed to start"
        log_msg "Checking hostapd output..."
        hostapd /tmp/hostapd.conf -d 2>&1 | head -20 >> $LOG_FILE
        return 1
    fi
}

start_dnsmasq() {
    log_msg "Starting dnsmasq for DHCP..."
    
    # Kill any existing dnsmasq on our interface
    killall dnsmasq 2>/dev/null
    sleep 1
    
    # Start dnsmasq
    dnsmasq -C /tmp/dnsmasq-hotspot.conf >> $LOG_FILE 2>&1
    
    # Check if it started
    sleep 1
    
    if pgrep -x dnsmasq > /dev/null; then
        log_msg "dnsmasq started successfully"
        return 0
    else
        log_msg "WARNING: dnsmasq failed to start, checking for port conflicts..."
        # Try to start on alternate port
        dnsmasq -C /tmp/dnsmasq-hotspot.conf --port=5353 >> $LOG_FILE 2>&1
        if pgrep -x dnsmasq > /dev/null; then
            log_msg "dnsmasq started on alternate port"
            return 0
        fi
        log_msg "ERROR: dnsmasq failed to start"
        return 1
    fi
}

check_status() {
    # Check if hostapd is running
    if pgrep -x hostapd > /dev/null; then
        return 0
    fi
    return 1
}

get_ip() {
    ip addr show $WLAN_INTERFACE 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1
}

get_current_hostname() {
    # Return the mDNS hostname
    if [ -n "$MDNS_HOSTNAME" ]; then
        echo "$MDNS_HOSTNAME"
    else
        hostname
    fi
}

verify_hotspot() {
    log_msg "Verifying hotspot setup..."
    
    # Check hostapd
    if ! pgrep -x hostapd > /dev/null; then
        log_msg "ERROR: hostapd is not running"
        return 1
    fi
    
    # Check IP
    IP=$(get_ip)
    if [ -z "$IP" ]; then
        log_msg "ERROR: No IP address on $WLAN_INTERFACE"
        return 1
    fi
    
    # Check dnsmasq (optional but recommended)
    if ! pgrep -x dnsmasq > /dev/null; then
        log_msg "WARNING: dnsmasq is not running (DHCP may not work)"
    fi
    
    # Check avahi
    if pgrep -x avahi-daemon > /dev/null; then
        log_msg "mDNS is active: ${MDNS_HOSTNAME}.local"
    else
        log_msg "WARNING: avahi-daemon not running (mDNS may not work)"
    fi
    
    log_msg "Hotspot verification passed"
    return 0
}

case $1 in
start)
    # Clear log file
    echo "===== Hotspot Start: $(date) =====" > $LOG_FILE
    
    if ! check_interface; then
        log_msg "Error: $WLAN_INTERFACE not found!"
        echo "HOTSPOT_STATUS=failed"
        exit 1
    fi
    
    # Generate hostname from MAC address
    generate_hostname
    
    # Step 1: Disconnect from WiFi and kill interfering processes
    disconnect_wifi
    
    # Step 2: Setup interface with static IP
    if ! setup_interface; then
        log_msg "Failed to setup interface, retrying..."
        sleep 2
        setup_interface
    fi
    
    # Step 3: Create configurations
    create_hostapd_config
    create_dnsmasq_config
    
    # Step 4: Start hostapd
    if ! start_hostapd; then
        log_msg "Hostapd failed, trying with different driver..."
        # Try without specifying driver
        sed -i 's/driver=nl80211/#driver=nl80211/' /tmp/hostapd.conf
        if ! start_hostapd; then
            echo "HOTSPOT_STATUS=failed"
            echo "Check log: $LOG_FILE"
            exit 1
        fi
    fi
    
    # Step 5: Start dnsmasq for DHCP
    start_dnsmasq
    
    # Step 6: Setup mDNS with Avahi
    setup_avahi
    
    # Step 7: Final verification
    sleep 2
    
    if verify_hotspot; then
        IP=$(get_ip)
        [ -z "$IP" ] && IP=$HOTSPOT_IP
        
        log_msg "===== Hotspot Active ====="
        log_msg "SSID: $HOSTAPD_SSID"
        log_msg "IP: $IP"
        log_msg "Hostname: ${MDNS_HOSTNAME}.local"
        
        echo "HOTSPOT_STATUS=active"
        echo "HOTSPOT_SSID=$HOSTAPD_SSID"
        echo "HOTSPOT_PASSWORD=$HOSTAPD_PASSWD"
        echo "HOTSPOT_IP=$IP"
        echo "HOTSPOT_HOSTNAME=${MDNS_HOSTNAME}.local"
        exit 0
    else
        echo "HOTSPOT_STATUS=failed"
        echo "Check log: $LOG_FILE"
        exit 1
    fi
    ;;
    
stop)
    log_msg "Stopping hotspot..."
    
    # Remove iptables rules
    iptables -t nat -D PREROUTING -i $WLAN_INTERFACE -p tcp --dport 80 -j REDIRECT --to-port $WEBAPP_PORT 2>/dev/null || true
    
    # Stop services
    killall hostapd 2>/dev/null
    killall dnsmasq 2>/dev/null
    
    # Stop avahi and remove service file
    rm -f /etc/avahi/services/webapp.service
    systemctl restart avahi-daemon 2>/dev/null
    
    # Clean up config files
    rm -f /tmp/hostapd.conf
    rm -f /tmp/dnsmasq-hotspot.conf
    rm -f /tmp/hostapd.pid
    rm -f /tmp/dnsmasq-hotspot.pid
    rm -f /tmp/avahi-daemon-hotspot.conf
    
    # Restore WiFi
    reconnect_wifi
    
    echo "HOTSPOT_STATUS=stopped"
    ;;
    
status)
    if check_status; then
        IP=$(get_ip)
        [ -z "$IP" ] && IP=$HOTSPOT_IP
        
        # Try to get hostname
        generate_hostname
        
        echo "HOTSPOT_STATUS=active"
        echo "HOTSPOT_SSID=$HOSTAPD_SSID"
        echo "HOTSPOT_PASSWORD=$HOSTAPD_PASSWD"
        echo "HOTSPOT_IP=$IP"
        echo "HOTSPOT_HOSTNAME=${MDNS_HOSTNAME}.local"
        exit 0
    else
        echo "HOTSPOT_STATUS=inactive"
        exit 1
    fi
    ;;

debug)
    echo "===== Hotspot Debug Info ====="
    echo ""
    
    # Generate hostname for display
    generate_hostname
    
    echo "Interface Status:"
    ip addr show $WLAN_INTERFACE
    echo ""
    echo "MAC Address: $(cat /sys/class/net/$WLAN_INTERFACE/address 2>/dev/null)"
    echo "Hostname: ${MDNS_HOSTNAME}.local"
    echo ""
    echo "Services:"
    echo "  hostapd:  $(pgrep -x hostapd > /dev/null && echo 'RUNNING' || echo 'STOPPED')"
    echo "  dnsmasq:  $(pgrep -x dnsmasq > /dev/null && echo 'RUNNING' || echo 'STOPPED')"
    echo "  avahi:    $(pgrep -x avahi-daemon > /dev/null && echo 'RUNNING' || echo 'STOPPED')"
    echo ""
    echo "Access URLs:"
    IP=$(get_ip)
    [ -z "$IP" ] && IP=$HOTSPOT_IP
    echo "  http://${IP}:8000/static/index.html"
    echo "  http://${MDNS_HOSTNAME}.local:8000/static/index.html"
    echo ""
    echo "Last 20 lines of log:"
    tail -20 $LOG_FILE 2>/dev/null
    ;;
    
*)
    echo "Usage: $0 [start|stop|status|debug]"
    echo ""
    echo "Commands:"
    echo "  start   - Start the Wi-Fi hotspot with mDNS"
    echo "  stop    - Stop the hotspot and restore Wi-Fi"
    echo "  status  - Show current hotspot status"
    echo "  debug   - Show detailed debug information"
    ;;
esac
