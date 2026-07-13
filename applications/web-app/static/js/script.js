// applications/web-app/static/js/script.js

//Copyright (c) 2025 STMicroelectronics. All rights reserved.
//
// This software component is licensed by ST under BSD 3-Clause license,
// the "License"; You may not use this file except in compliance with the
// License. You may obtain a copy of the License at:
//                        opensource.org/licenses/BSD-3-Clause

// Constants
const WS_URL = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws';
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
            // Handle voice command result from server
            if (data.voice_result) {
                handleVoiceResult(data.voice_result);
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

// Helper: send command if connected
function sendCommand(cmd) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(cmd));
    }
}

// Speed Limit Slider
const speedSlider = document.getElementById('speed-slider');
const speedValueLabel = document.getElementById('speed-value');

if (speedSlider) {
    speedSlider.addEventListener('input', function() {
        speedValueLabel.textContent = speedSlider.value;
        sendCommand({ max_speed: parseInt(speedSlider.value, 10) });
    });
}

// Left Joystick
let leftJoystick = {
    element: document.getElementById('left-joystick'),
    c1: document.querySelector('#left-joystick .c1'),
    maxMovement: 80,
    verticalValue: 0,
    isMoving: false,
    movementTimeout: null,
    touchId: null,
    mouseActive: false,
};

// Left joystick touch events
leftJoystick.c1.addEventListener('touchstart', handleLeftJoystickStart, false);
leftJoystick.c1.addEventListener('touchmove', handleLeftJoystickMove, false);
leftJoystick.c1.addEventListener('touchend', handleLeftJoystickEnd, false);
// Left joystick mouse events
leftJoystick.c1.addEventListener('mousedown', handleLeftJoystickMouseDown, false);
document.addEventListener('mousemove', handleLeftJoystickMouseMove, false);
document.addEventListener('mouseup', handleLeftJoystickMouseUp, false);

function handleLeftJoystickStart(event) {
    event.preventDefault();
    let touch = event.changedTouches[0];
    leftJoystick.touchId = touch.identifier;
    leftJoystick.isMoving = true;
    clearTimeout(leftJoystick.movementTimeout);
}

function handleLeftJoystickMove(event) {
    event.preventDefault();
    let touch = null;
    for (let i = 0; i < event.touches.length; i++) {
        if (event.touches[i].identifier === leftJoystick.touchId) {
            touch = event.touches[i];
            break;
        }
    }
    if (!touch) return;

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
    for (let i = 0; i < event.changedTouches.length; i++) {
        if (event.changedTouches[i].identifier === leftJoystick.touchId) {
            touch = event.changedTouches[i];
            break;
        }
    }
    if (!touch) return;

    leftJoystick.verticalValue = 0;
    leftJoystick.c1.style.transform = 'translateY(0px)';
    clearTimeout(leftJoystick.movementTimeout);
    leftJoystick.movementTimeout = setTimeout(() => {
        leftJoystick.isMoving = false;
    }, DATA_POLL_TIMEOUT);
    leftJoystick.touchId = null;
}

// Mouse handlers for left joystick
function handleLeftJoystickMouseDown(event) {
    event.preventDefault();
    leftJoystick.mouseActive = true;
    leftJoystick.isMoving = true;
    clearTimeout(leftJoystick.movementTimeout);
}

function handleLeftJoystickMouseMove(event) {
    if (!leftJoystick.mouseActive) return;
    event.preventDefault();
    let rect = leftJoystick.element.getBoundingClientRect();
    let y = event.clientY - rect.top - rect.height / 2;
    y = Math.max(-leftJoystick.maxMovement, Math.min(leftJoystick.maxMovement, y));
    leftJoystick.verticalValue = -Math.round((y / leftJoystick.maxMovement) * 100);
    leftJoystick.c1.style.transform = `translateY(${y}px)`;
    leftJoystick.isMoving = true;
    clearTimeout(leftJoystick.movementTimeout);
    leftJoystick.movementTimeout = setTimeout(() => {
        leftJoystick.isMoving = false;
    }, DATA_POLL_TIMEOUT);
}

function handleLeftJoystickMouseUp(event) {
    if (!leftJoystick.mouseActive) return;
    leftJoystick.mouseActive = false;
    leftJoystick.verticalValue = 0;
    leftJoystick.c1.style.transform = 'translateY(0px)';
    clearTimeout(leftJoystick.movementTimeout);
    leftJoystick.movementTimeout = setTimeout(() => {
        leftJoystick.isMoving = false;
    }, DATA_POLL_TIMEOUT);
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
    touchId: null,
    mouseActive: false,
};

// Right joystick touch events
rightJoystick.c1.addEventListener('touchstart', handleRightJoystickStart, false);
rightJoystick.c1.addEventListener('touchmove', handleRightJoystickMove, false);
rightJoystick.c1.addEventListener('touchend', handleRightJoystickEnd, false);
// Right joystick mouse events
rightJoystick.c1.addEventListener('mousedown', handleRightJoystickMouseDown, false);
document.addEventListener('mousemove', handleRightJoystickMouseMove, false);
document.addEventListener('mouseup', handleRightJoystickMouseUp, false);

function handleRightJoystickStart(event) {
    event.preventDefault();
    let touch = event.changedTouches[0];
    rightJoystick.touchId = touch.identifier;
    rightJoystick.isMoving = true;
    clearTimeout(rightJoystick.movementTimeout);
}

function handleRightJoystickMove(event) {
    event.preventDefault();
    let touch = null;
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
    for (let i = 0; i < event.changedTouches.length; i++) {
        if (event.changedTouches[i].identifier === rightJoystick.touchId) {
            touch = event.changedTouches[i];
            break;
        }
    }
    if (!touch) return;

    rightJoystick.horizontalValue = 0;
    rightJoystick.verticalValue = 0;
    rightJoystick.c1.style.transform = 'translate(0px, 0px)';
    clearTimeout(rightJoystick.movementTimeout);
    rightJoystick.movementTimeout = setTimeout(() => {
        rightJoystick.isMoving = false;
    }, DATA_POLL_TIMEOUT);
    rightJoystick.touchId = null;
}

// Mouse handlers for right joystick
function handleRightJoystickMouseDown(event) {
    event.preventDefault();
    rightJoystick.mouseActive = true;
    rightJoystick.isMoving = true;
    clearTimeout(rightJoystick.movementTimeout);
}

function handleRightJoystickMouseMove(event) {
    if (!rightJoystick.mouseActive) return;
    event.preventDefault();
    let rect = rightJoystick.element.getBoundingClientRect();
    let x = event.clientX - rect.left - rect.width / 2;
    let y = event.clientY - rect.top - rect.height / 2;
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

function handleRightJoystickMouseUp(event) {
    if (!rightJoystick.mouseActive) return;
    rightJoystick.mouseActive = false;
    rightJoystick.horizontalValue = 0;
    rightJoystick.verticalValue = 0;
    rightJoystick.c1.style.transform = 'translate(0px, 0px)';
    clearTimeout(rightJoystick.movementTimeout);
    rightJoystick.movementTimeout = setTimeout(() => {
        rightJoystick.isMoving = false;
    }, DATA_POLL_TIMEOUT);
}

// Right Joystick Dial Rotation
// hitElement is the enlarged touch target (.outer-dial, see styles.css);
// visualElement (.c5) is the ring that actually shows the rotation. Both
// are concentric, so angle calculations are identical for either, but
// binding listeners to the larger hitElement makes the dial actually
// grabbable instead of relying on the ~30px sliver of .c5 outside the
// inner joystick.
let rightDial = {
    element: document.querySelector('#right-joystick .outer-dial'),
    visualElement: document.querySelector('#right-joystick .c5'),
    rotationValue: 0,
    isRotating: false,
    rotationTimeout: null,
    touchId: null,
    startAngle: 0,
    mouseActive: false,
};

// Dial rotation touch events
rightDial.element.addEventListener('touchstart', handleDialStart, false);
rightDial.element.addEventListener('touchmove', handleDialRotate, false);
rightDial.element.addEventListener('touchend', handleDialEnd, false);
// Dial rotation mouse events
rightDial.element.addEventListener('mousedown', handleDialMouseDown, false);
document.addEventListener('mousemove', handleDialMouseMove, false);
document.addEventListener('mouseup', handleDialMouseUp, false);

function getAngle(center, point) {
    const dy = point.y - center.y;
    const dx = point.x - center.x;
    let theta = Math.atan2(dy, dx);
    theta *= 180 / Math.PI;
    theta = (theta + 360) % 360;
    return theta;
}

function handleDialStart(event) {
    event.preventDefault();
    let touch = event.changedTouches[0];
    rightDial.touchId = touch.identifier;
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

    if (rotation > 180) {
        rotation -= 360;
    }
    rotation = Math.max(-180, Math.min(180, rotation));

    rightDial.rotationValue = rotation;
    rightDial.visualElement.style.transform = `rotate(${rotation}deg)`;

    rightDial.isRotating = true;
    clearTimeout(rightDial.rotationTimeout);
    rightDial.rotationTimeout = setTimeout(() => {
        rightDial.isRotating = false;
    }, DATA_POLL_TIMEOUT);
}

function handleDialEnd(event) {
    event.preventDefault();
    let touch = null;
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

    rightDial.touchId = null;
    rightDial.rotationValue = 0;
    rightDial.visualElement.style.transform = 'rotate(0deg)';
}

// Mouse handlers for dial rotation
function handleDialMouseDown(event) {
    event.preventDefault();
    rightDial.mouseActive = true;
    rightDial.isRotating = true;
    clearTimeout(rightDial.rotationTimeout);
    const rect = rightDial.element.getBoundingClientRect();
    const center = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    rightDial.startAngle = getAngle(center, { x: event.clientX, y: event.clientY }) - rightDial.rotationValue;
}

function handleDialMouseMove(event) {
    if (!rightDial.mouseActive) return;
    event.preventDefault();
    const rect = rightDial.element.getBoundingClientRect();
    const center = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    let angle = getAngle(center, { x: event.clientX, y: event.clientY });
    let rotation = (angle - rightDial.startAngle + 360) % 360;
    if (rotation > 180) rotation -= 360;
    rotation = Math.max(-180, Math.min(180, rotation));
    rightDial.rotationValue = rotation;
    rightDial.visualElement.style.transform = `rotate(${rotation}deg)`;
    rightDial.isRotating = true;
    clearTimeout(rightDial.rotationTimeout);
    rightDial.rotationTimeout = setTimeout(() => {
        rightDial.isRotating = false;
    }, DATA_POLL_TIMEOUT);
}

function handleDialMouseUp(event) {
    if (!rightDial.mouseActive) return;
    rightDial.mouseActive = false;
    clearTimeout(rightDial.rotationTimeout);
    rightDial.rotationTimeout = setTimeout(() => {
        rightDial.isRotating = false;
    }, DATA_POLL_TIMEOUT);
    rightDial.rotationValue = 0;
    rightDial.visualElement.style.transform = 'rotate(0deg)';
}

// =============================================================================
// KEYBOARD CONTROLS
// =============================================================================
let keyboardState = {
    forward: false,
    backward: false,
    turnLeft: false,
    turnRight: false,
    rotateLeft: false,
    rotateRight: false,
};

const KEY_SPEED = 70;

function sendKeyboardCommands() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    let throttle = 0;
    let dirX = 0;
    let dirRot = 0;

    if (keyboardState.forward) throttle = KEY_SPEED;
    if (keyboardState.backward) throttle = -KEY_SPEED;
    if (keyboardState.turnLeft) dirX = -KEY_SPEED;
    if (keyboardState.turnRight) dirX = KEY_SPEED;
    if (keyboardState.rotateLeft) dirRot = -KEY_SPEED;
    if (keyboardState.rotateRight) dirRot = KEY_SPEED;

    sendCommand({
        [FIELD_STR_THROTTLE]: throttle,
        [FIELD_STR_DIR_X]: dirX,
        [FIELD_STR_DIR_Y]: 0,
        [FIELD_STR_DIR_ROT]: dirRot
    });
}

document.addEventListener('keydown', function(e) {
    let handled = true;
    switch(e.key) {
        case 'w': case 'W': case 'ArrowUp':
            keyboardState.forward = true; break;
        case 's': case 'S': case 'ArrowDown':
            keyboardState.backward = true; break;
        case 'a': case 'A': case 'ArrowLeft':
            keyboardState.turnLeft = true; break;
        case 'd': case 'D': case 'ArrowRight':
            keyboardState.turnRight = true; break;
        case 'q': case 'Q':
            keyboardState.rotateLeft = true; break;
        case 'e': case 'E':
            keyboardState.rotateRight = true; break;
        case '1':
            selectMode('locked'); handled = false; break;
        case '2':
            selectMode('controller'); handled = false; break;
        case '3':
            selectMode('hybrid'); handled = false; break;
        case '4':
            selectMode('follow-me'); handled = false; break;
        case '5':
            selectMode('autopilot'); handled = false; break;
        default:
            handled = false;
    }
    if (handled) e.preventDefault();
    sendKeyboardCommands();
});

document.addEventListener('keyup', function(e) {
    let handled = true;
    switch(e.key) {
        case 'w': case 'W': case 'ArrowUp':
            keyboardState.forward = false; break;
        case 's': case 'S': case 'ArrowDown':
            keyboardState.backward = false; break;
        case 'a': case 'A': case 'ArrowLeft':
            keyboardState.turnLeft = false; break;
        case 'd': case 'D': case 'ArrowRight':
            keyboardState.turnRight = false; break;
        case 'q': case 'Q':
            keyboardState.rotateLeft = false; break;
        case 'e': case 'E':
            keyboardState.rotateRight = false; break;
        default:
            handled = false;
    }
    if (handled) e.preventDefault();
    sendKeyboardCommands();
});

// =============================================================================
// VOICE CONTROL (Web Speech API -> intent classifier on the board)
// =============================================================================
const voiceButton = document.getElementById('voice-button');
const voiceStatus = document.getElementById('voice-status');
const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let voiceActive = false;

function setVoiceStatus(text) {
    if (voiceStatus) voiceStatus.textContent = text;
}

function handleVoiceResult(result) {
    if (result.error) {
        setVoiceStatus(result.error);
    } else if (result.note === 'locked') {
        setVoiceStatus('Locked - unlock to use voice');
    } else if (result.intent) {
        setVoiceStatus(`Heard: ${result.intent}${result.value ? ' ' + result.value : ''}`);
    } else {
        setVoiceStatus('Not understood');
    }
}

if (SpeechRecognitionAPI && voiceButton) {
    recognition = new SpeechRecognitionAPI();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onresult = function(event) {
        const transcript = event.results[event.results.length - 1][0].transcript.trim();
        if (!transcript) return;
        debugLog('Voice heard: ' + transcript);
        setVoiceStatus(`"${transcript}"`);
        sendCommand({ voice_text: transcript });
    };

    recognition.onerror = function(e) {
        debugLog('Speech recognition error: ' + e.error);
        if (e.error === 'no-speech' || e.error === 'aborted') return;
        setVoiceStatus('Mic error: ' + e.error);
    };

    recognition.onend = function() {
        // Browsers auto-stop recognition periodically; restart while active.
        if (voiceActive) recognition.start();
    };

    voiceButton.addEventListener('click', function() {
        voiceActive = !voiceActive;
        voiceButton.classList.toggle('active', voiceActive);
        if (voiceActive) {
            setVoiceStatus('Listening...');
            recognition.start();
        } else {
            setVoiceStatus('Voice off');
            recognition.stop();
        }
    });
} else if (voiceButton) {
    voiceButton.disabled = true;
    setVoiceStatus('Voice not supported in this browser');
}

// =============================================================================
// MODE SELECTOR
// =============================================================================
const modes = ['locked', 'controller', 'hybrid', 'follow-me', 'autopilot'];
const modeButtons = document.querySelectorAll('.mode-button');

function selectMode(mode) {
    modeButtons.forEach(btn => btn.classList.remove('selected'));
    const btn = document.querySelector(`[data-mode="${mode}"]`);
    if (btn) btn.classList.add('selected');
    sendCommand({ [FIELD_STR_MODE]: mode });
}

modeButtons.forEach(button => {
    button.addEventListener('click', () => {
        const mode = button.getAttribute('data-mode');
        selectMode(mode);
    });
});

// Set default selected mode
document.getElementById('mode-locked').classList.add('selected');

// =============================================================================
// POLLING: Send joystick + dial state at regular interval
// =============================================================================
setInterval(() => {
    // Left joystick throttle command
    if (leftJoystick.isMoving) {
        sendCommand({ [FIELD_STR_THROTTLE]: leftJoystick.verticalValue });
    }

    // Right joystick direction command
    if (rightJoystick.isMoving) {
        sendCommand({
            [FIELD_STR_DIR_X]: rightJoystick.horizontalValue,
            [FIELD_STR_DIR_Y]: rightJoystick.verticalValue
        });
    }

    // Right joystick dial rotation command
    if (rightDial.isRotating) {
        const rotationValue = Math.round((rightDial.rotationValue / 180) * 100);
        sendCommand({ [FIELD_STR_DIR_ROT]: rotationValue });
    }

    // Keyboard state polling — send held keys at regular interval
    if (keyboardState.forward || keyboardState.backward ||
        keyboardState.turnLeft || keyboardState.turnRight ||
        keyboardState.rotateLeft || keyboardState.rotateRight) {
        sendKeyboardCommands();
    }
}, DATA_POLL_INTERVAL);

// =============================================================================
// FULL-SCREEN TOGGLE
// =============================================================================
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
        elem.requestFullscreen().then(() => { lockOrientation(); }).catch(err => {
            console.error(`Error attempting to enable full-screen mode: ${err.message} (${err.name})`);
        });
    } else if (elem.webkitRequestFullscreen) {
        elem.webkitRequestFullscreen();
        lockOrientation();
    } else if (elem.msRequestFullscreen) {
        elem.msRequestFullscreen();
        lockOrientation();
    }
    isFullscreen = true;
}

function exitFullscreen() {
    if (document.exitFullscreen) {
        document.exitFullscreen().then(() => { unlockOrientation(); }).catch(err => {
            console.error(`Error attempting to exit full-screen mode: ${err.message} (${err.name})`);
        });
    } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
        unlockOrientation();
    } else if (document.msExitFullscreen) {
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
    }
}

document.addEventListener('fullscreenchange', () => {
    isFullscreen = !!document.fullscreenElement;
});
