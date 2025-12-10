// applications/web-app/static/js/script.js

//Copyright (c) 2025 STMicroelectronics. All rights reserved.
//
// This software component is licensed by ST under BSD 3-Clause license,
// the "License"; You may not use this file except in compliance with the
// License. You may obtain a copy of the License at:
//                        opensource.org/licenses/BSD-3-Clause

// Constants
const WS_URL = 'ws://' + window.location.host + '/ws';
const FIELD_STR_THROTTLE = 'throttle';
const FIELD_STR_DIR_X = 'dir_x';
const FIELD_STR_DIR_Y = 'dir_y';
const FIELD_STR_DIR_ROT = 'dir_rot';
const FIELD_STR_MODE = 'mode';
const FIELD_STR_AZIMUTH = 'azimuth';
const FIELD_STR_DRIVE_TYPE = 'drive_type';

const DEBUG = false;
const DATA_POLL_INTERVAL = 150;
const DATA_POLL_TIMEOUT = 350;
const WS_RECONNECT_DELAY = 3000;

// Drive Type Indicator Element
const driveTypeLabel = document.getElementById('drive-type-label');

function debugLog(message) {
    if (DEBUG) {
        console.log(message);
    }
}

// Update drive type indicator in UI
function updateDriveTypeIndicator(driveType) {
    if (!driveTypeLabel) return;
    
    // Remove all existing classes
    driveTypeLabel.classList.remove('mecanum', 'differential', 'error');
    
    if (driveType === 'mecanum') {
        driveTypeLabel.textContent = '🔄 Mecanum Drive';
        driveTypeLabel.classList.add('mecanum');
    } else if (driveType === 'differential') {
        driveTypeLabel.textContent = '🚗 Differential Drive';
        driveTypeLabel.classList.add('differential');
    } else {
        driveTypeLabel.textContent = driveType || 'Unknown';
    }
}

// WebSocket connection with reconnection support
let ws = null;
let wsReconnectTimer = null;

function connectWebSocket() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        return; // Already connected
    }
    
    ws = new WebSocket(WS_URL);
    
    ws.onopen = function() {
        debugLog('WebSocket connection established');
        if (driveTypeLabel) {
            driveTypeLabel.textContent = 'Connected';
            driveTypeLabel.classList.remove('error');
        }
        // Request drive type info from server
        ws.send(JSON.stringify({ request: 'drive_type' }));
    };
    
    ws.onmessage = function(event) {
        debugLog('Received message: ' + event.data);
        try {
            const data = JSON.parse(event.data);
            // Handle drive type message from server
            if (data.drive_type) {
                updateDriveTypeIndicator(data.drive_type);
            }
        } catch (e) {
            debugLog('Failed to parse message: ' + e);
        }
    };
    
    ws.onclose = function() {
        debugLog('WebSocket connection closed');
        if (driveTypeLabel) {
            driveTypeLabel.textContent = 'Disconnected';
            driveTypeLabel.classList.add('error');
        }
        // Attempt to reconnect
        if (!wsReconnectTimer) {
            wsReconnectTimer = setTimeout(function() {
                wsReconnectTimer = null;
                connectWebSocket();
            }, WS_RECONNECT_DELAY);
        }
    };
    
    ws.onerror = function(error) {
        debugLog('WebSocket error: ' + error);
        if (driveTypeLabel) {
            driveTypeLabel.textContent = 'Connection Error';
            driveTypeLabel.classList.add('error');
        }
    };
}

// Initialize WebSocket connection
connectWebSocket();

// Left Joystick
let leftJoystick = {
    element: document.getElementById('left-joystick'),
    c1: document.querySelector('#left-joystick .c1'),
    maxMovement: 80,
    verticalValue: 0,
    isMoving: false,
    movementTimeout: null,
    touchId: null,
};

// Left joystick events
leftJoystick.c1.addEventListener('touchstart', handleLeftJoystickStart, false);
leftJoystick.c1.addEventListener('touchmove', handleLeftJoystickMove, false);
leftJoystick.c1.addEventListener('touchend', handleLeftJoystickEnd, false);

function handleLeftJoystickStart(event) {
    event.preventDefault();
    let touch = event.changedTouches[0];
    leftJoystick.touchId = touch.identifier; // Store touch identifier
    leftJoystick.isMoving = true;
    clearTimeout(leftJoystick.movementTimeout);
}

function handleLeftJoystickMove(event) {
    event.preventDefault();
    let touch = null;
    // Find the touch that matches the stored identifier
    for (let i = 0; i < event.touches.length; i++) {
        if (event.touches[i].identifier === leftJoystick.touchId) {
            touch = event.touches[i];
            break;
        }
    }
    if (!touch) return; // Exit if touch not found

    let rect = leftJoystick.element.getBoundingClientRect();
    let y = touch.clientY - rect.top - rect.height / 2;
    y = Math.max(-leftJoystick.maxMovement, Math.min(leftJoystick.maxMovement, y));
    leftJoystick.verticalValue = -Math.round((y / leftJoystick.maxMovement) * 100);
    leftJoystick.c1.style.transform = `translateY(${y}px)`;

    leftJoystick.isMoving = true;
    clearTimeout(leftJoystick.movementTimeout);
    leftJoystick.movementTimeout = setTimeout(() => {
        leftJoystick.isMoving = false;
    }, DATA_POLL_TIMEOUT);
}

function handleLeftJoystickEnd(event) {
    event.preventDefault();
    let touch = null;
    // Find the touch that matches the stored identifier
    for (let i = 0; i < event.changedTouches.length; i++) {
        if (event.changedTouches[i].identifier === leftJoystick.touchId) {
            touch = event.changedTouches[i];
            break;
        }
    }
    if (!touch) return;

    leftJoystick.verticalValue = 0;
    leftJoystick.c1.style.transform = `translateY(0px)`;

    clearTimeout(leftJoystick.movementTimeout);
    leftJoystick.movementTimeout = setTimeout(() => {
        leftJoystick.isMoving = false;
    }, DATA_POLL_TIMEOUT);

    leftJoystick.touchId = null; // Reset touch identifier
}

// Right Joystick (Thumb)
let rightJoystick = {
    element: document.querySelector('#right-joystick .joystick-inner'),
    c1: document.querySelector('#right-joystick .joystick-inner .c1'),
    maxMovement: 80,
    horizontalValue: 0,
    verticalValue: 0,
    isMoving: false,
    movementTimeout: null,
    touchId: null, // Track the touch point
};

// Right joystick events
rightJoystick.c1.addEventListener('touchstart', handleRightJoystickStart, false);
rightJoystick.c1.addEventListener('touchmove', handleRightJoystickMove, false);
rightJoystick.c1.addEventListener('touchend', handleRightJoystickEnd, false);

function handleRightJoystickStart(event) {
    event.preventDefault();
    let touch = event.changedTouches[0];
    rightJoystick.touchId = touch.identifier; // Store touch identifier
    rightJoystick.isMoving = true;
    clearTimeout(rightJoystick.movementTimeout);
}

function handleRightJoystickMove(event) {
    event.preventDefault();
    let touch = null;
    // Find the touch that matches the stored identifier
    for (let i = 0; i < event.touches.length; i++) {
        if (event.touches[i].identifier === rightJoystick.touchId) {
            touch = event.touches[i];
            break;
        }
    }
    if (!touch) return;

    let rect = rightJoystick.element.getBoundingClientRect();
    let x = touch.clientX - rect.left - rect.width / 2;
    let y = touch.clientY - rect.top - rect.height / 2;
    x = Math.max(-rightJoystick.maxMovement, Math.min(rightJoystick.maxMovement, x));
    y = Math.max(-rightJoystick.maxMovement, Math.min(rightJoystick.maxMovement, y));
    rightJoystick.horizontalValue = Math.round((x / rightJoystick.maxMovement) * 100);
    rightJoystick.verticalValue = -Math.round((y / rightJoystick.maxMovement) * 100);
    rightJoystick.c1.style.transform = `translate(${x}px, ${y}px)`;

    rightJoystick.isMoving = true;
    clearTimeout(rightJoystick.movementTimeout);
    rightJoystick.movementTimeout = setTimeout(() => {
        rightJoystick.isMoving = false;
    }, DATA_POLL_TIMEOUT);
}

function handleRightJoystickEnd(event) {
    event.preventDefault();
    let touch = null;
    // Find the touch that matches the stored identifier
    for (let i = 0; i < event.changedTouches.length; i++) {
        if (event.changedTouches[i].identifier === rightJoystick.touchId) {
            touch = event.changedTouches[i];
            break;
        }
    }
    if (!touch) return;

    rightJoystick.horizontalValue = 0;
    rightJoystick.verticalValue = 0;
    rightJoystick.c1.style.transform = `translate(0px, 0px)`;
    clearTimeout(rightJoystick.movementTimeout);
    rightJoystick.movementTimeout = setTimeout(() => {
        rightJoystick.isMoving = false;
    }, DATA_POLL_TIMEOUT);
 
    rightJoystick.touchId = null; // Reset touch identifier
}

// Right Joystick Dial Rotation
let rightDial = {
    element: document.querySelector('#right-joystick .c5'),
    rotationValue: 0,
    isRotating: false,
    //isMoving: false,
    //movementTimeout: null,
    rotationTimeout: null,
    touchId: null, // Track the touch point
    startAngle: 0,
};

// Dial rotation events
rightDial.element.addEventListener('touchstart', handleDialStart, false);
rightDial.element.addEventListener('touchmove', handleDialRotate, false);
rightDial.element.addEventListener('touchend', handleDialEnd, false);

function getAngle(center, point) {
    const dy = point.y - center.y;
    const dx = point.x - center.x;
    let theta = Math.atan2(dy, dx); // Radians
    theta *= 180 / Math.PI; // Degrees
    theta = (theta + 360) % 360; // Normalize
    return theta;
}

function handleDialStart(event) {
    event.preventDefault();
    let touch = event.changedTouches[0];
    rightDial.touchId = touch.identifier; // Store touch identifier
    rightDial.isRotating = true;
    clearTimeout(rightDial.rotationTimeout);

    const rect = rightDial.element.getBoundingClientRect();
    const center = {
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
    };
    const point = {
        x: touch.clientX,
        y: touch.clientY,
    };
    rightDial.startAngle = getAngle(center, point) - rightDial.rotationValue;
}

function handleDialRotate(event) {
    if (!rightDial.isRotating) return;
    event.preventDefault();
    let touch = null;
    // Find the touch that matches the stored identifier
    for (let i = 0; i < event.touches.length; i++) {
        if (event.touches[i].identifier === rightDial.touchId) {
            touch = event.touches[i];
            break;
        }
    }
    if (!touch) return;

    const rect = rightDial.element.getBoundingClientRect();
    const center = {
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
    };
    const point = {
        x: touch.clientX,
        y: touch.clientY,
    };
    let angle = getAngle(center, point);
    let rotation = (angle - rightDial.startAngle + 360) % 360;

    // Restrict rotation to 180 degrees in either direction
    if (rotation > 180) {
        rotation -= 360;
    }
    rotation = Math.max(-180, Math.min(180, rotation));

    rightDial.rotationValue = rotation;
    rightDial.element.style.transform = `rotate(${rotation}deg)`;

    rightDial.isRotating = true;
    clearTimeout(rightDial.rotationTimeout);
    rightDial.rotationTimeout = setTimeout(() => {
        rightDial.isRotating = false;
    }, DATA_POLL_TIMEOUT);
}

function handleDialEnd(event) {
    event.preventDefault();
    let touch = null;
    // Find the touch that matches the stored identifier
    for (let i = 0; i < event.changedTouches.length; i++) {
        if (event.changedTouches[i].identifier === rightDial.touchId) {
            touch = event.changedTouches[i];
            break;
        }
    }
    if (!touch) return;

    clearTimeout(rightDial.rotationTimeout);
    rightDial.rotationTimeout = setTimeout(() => {
        rightDial.isRotating = false;
    }, DATA_POLL_TIMEOUT);

    rightDial.touchId = null; // Reset touch identifier

    // Reset rotation to original position
    rightDial.rotationValue = 0;
    rightDial.element.style.transform = `rotate(0deg)`;
}

// Mode Selector
const modes = ['locked', 'controller', 'follow-me', 'autopilot'];
const modeButtons = document.querySelectorAll('.mode-button');


function sendCommands() {
    const command = { [FIELD_STR_MODE]: "controller" };
    ws.send(JSON.stringify(command));

    setTimeout(() => {
        const throttleCommand = { [FIELD_STR_THROTTLE]: 50 };
        ws.send(JSON.stringify(throttleCommand));
    }, 3000);

    setTimeout(() => {
        const throttleCommand = { [FIELD_STR_THROTTLE]: 0 };
        ws.send(JSON.stringify(throttleCommand));
    }, 6000);

    setTimeout(() => {
        const directionCommand = {
            [FIELD_STR_DIR_X]: 100,
            [FIELD_STR_DIR_Y]: 0
        };
        const throttleCommand = { [FIELD_STR_THROTTLE]: 50 };
    
        ws.send(JSON.stringify(directionCommand));
        ws.send(JSON.stringify(throttleCommand));
        
    }, 7000);

    setTimeout(() => {
        const stopCommand = { [FIELD_STR_THROTTLE]: 0 };
        const directionCommandStop = {
            [FIELD_STR_DIR_X]: 0,
            [FIELD_STR_DIR_Y]: 0
        };
        ws.send(JSON.stringify(directionCommandStop));
        ws.send(JSON.stringify(stopCommand));
    }, 10000);

    setTimeout(() => {
        const rotationValue = 50;
        const rotationCommand = { [FIELD_STR_DIR_ROT]: rotationValue };
        ws.send(JSON.stringify(rotationCommand));
    }, 12000);

    setTimeout(() => {
        const rotationValue = 0;
        const rotationCommand = { [FIELD_STR_DIR_ROT]: rotationValue };
        ws.send(JSON.stringify(rotationCommand));
    }, 15000);
}

// Run the sequence every 16 seconds (to repeat the entire cycle)
//setInterval(sendCommands, 16000);


modeButtons.forEach(button => {
    button.addEventListener('click', () => {
        // Remove 'selected' class from all buttons
        modeButtons.forEach(btn => btn.classList.remove('selected'));
        // Add 'selected' class to the clicked button
        button.classList.add('selected');
        // Get the mode from data attribute
        const mode = button.getAttribute('data-mode');
        // Send the mode command
        const command = { [FIELD_STR_MODE]: mode };
        ws.send(JSON.stringify(command));
    });
});

// Set default selected mode
document.getElementById('mode-locked').classList.add('selected');

// Sampling and sending commands every 200ms
setInterval(() => {
    // Left joystick throttle command
    if (leftJoystick.isMoving) {
        const throttleCommand = { [FIELD_STR_THROTTLE]: leftJoystick.verticalValue };
        ws.send(JSON.stringify(throttleCommand));
    }

    // Right joystick direction command
    if (rightJoystick.isMoving) {
        const directionCommand = {
            [FIELD_STR_DIR_X]: rightJoystick.horizontalValue,
            [FIELD_STR_DIR_Y]: rightJoystick.verticalValue
        };
        ws.send(JSON.stringify(directionCommand));
    }

    // Right joystick dial rotation command
    if (rightDial.isRotating) {
        const rotationValue = Math.round((rightDial.rotationValue / 180) * 100);
        const rotationCommand = { [FIELD_STR_DIR_ROT]: rotationValue };
        ws.send(JSON.stringify(rotationCommand));
    }
}, DATA_POLL_INTERVAL);

// Full-Screen Toggle Button
const fullscreenButton = document.getElementById('fullscreen-button');
let isFullscreen = false;

fullscreenButton.addEventListener('click', () => {
    if (!isFullscreen) {
        enterFullscreen();
    } else {
        exitFullscreen();
    }
});

function enterFullscreen() {
    const elem = document.documentElement;

    if (elem.requestFullscreen) {
        elem.requestFullscreen().then(() => {
            lockOrientation();
        }).catch(err => {
            console.error(`Error attempting to enable full-screen mode: ${err.message} (${err.name})`);
        });
    } else if (elem.webkitRequestFullscreen) { /* Safari */
        elem.webkitRequestFullscreen();
        lockOrientation();
    } else if (elem.msRequestFullscreen) { /* IE11 */
        elem.msRequestFullscreen();
        lockOrientation();
    }

    isFullscreen = true;
}

function exitFullscreen() {
    if (document.exitFullscreen) {
        document.exitFullscreen().then(() => {
            unlockOrientation();
        }).catch(err => {
            console.error(`Error attempting to exit full-screen mode: ${err.message} (${err.name})`);
        });
    } else if (document.webkitExitFullscreen) { /* Safari */
        document.webkitExitFullscreen();
        unlockOrientation();
    } else if (document.msExitFullscreen) { /* IE11 */
        document.msExitFullscreen();
        unlockOrientation();
    }

    isFullscreen = false;
}

function lockOrientation() {
    if (screen.orientation && screen.orientation.lock) {
        screen.orientation.lock('landscape').then(() => {
            console.log('Orientation locked to landscape');
        }).catch(err => {
            console.error(`Error locking orientation: ${err.message} (${err.name})`);
        });
    } else {
        console.warn('Orientation lock not supported on this device.');
    }
}

function unlockOrientation() {
    if (screen.orientation && screen.orientation.unlock) {
        screen.orientation.unlock();
        console.log('Orientation unlocked');
    } else {
        console.warn('Orientation unlock not supported on this device.');
    }
}

// Listen for fullscreen change events to update button state
document.addEventListener('fullscreenchange', () => {
    isFullscreen = !!document.fullscreenElement;
});
