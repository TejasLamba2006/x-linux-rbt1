// applications/web-app/static/js/script.js

// Constants
const WS_URL = 'ws://' + window.location.host + '/ws';
const COMMAND_THROTTLE = 'throttle';
const COMMAND_DIR_X = 'dir_x';
const COMMAND_DIR_Y = 'dir_y';
const COMMAND_DIR_ROT = 'dir_rot';
const COMMAND_MODE = 'mode';

// Establish WebSocket connection
let ws = new WebSocket(WS_URL);

ws.onopen = function() {
    console.log('WebSocket connection established');
};

ws.onmessage = function(event) {
    console.log('Received message: ' + event.data);
};

// Left Joystick
let leftJoystick = {
    element: document.getElementById('left-joystick'),
    c1: document.querySelector('#left-joystick .c1'),
    maxMovement: 80,
    verticalValue: 0,
    isMoving: false,
    movementTimeout: null,
    touchId: null, // Track the touch point
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
    }, 200);
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

    leftJoystick.isMoving = false;
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
    }, 200);
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

    rightJoystick.isMoving = false;
    rightJoystick.touchId = null; // Reset touch identifier
}

// Right Joystick Dial Rotation
let rightDial = {
    element: document.querySelector('#right-joystick .c5'),
    rotationValue: 0,
    isRotating: false,
    isMoving: false,
    movementTimeout: null,
    touchId: null, // Track the touch point
};

// Dial rotation events
rightDial.element.addEventListener('touchstart', handleDialStart, false);
rightDial.element.addEventListener('touchmove', handleDialMove, false);
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
    rightDial.isMoving = true;
    clearTimeout(rightDial.movementTimeout);

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

function handleDialMove(event) {
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
    const angle = getAngle(center, point);
    rightDial.rotationValue = (angle - rightDial.startAngle + 360) % 360;
    rightDial.element.style.transform = `rotate(${rightDial.rotationValue}deg)`;

    rightDial.isMoving = true;
    clearTimeout(rightDial.movementTimeout);
    rightDial.movementTimeout = setTimeout(() => {
        rightDial.isMoving = false;
    }, 200);
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

    rightDial.isRotating = false;
    rightDial.isMoving = false;
    rightDial.touchId = null; // Reset touch identifier
}

// Mode Selector
const modes = ['locked', 'controller', 'follow-me', 'autopilot'];
const modeButtons = document.querySelectorAll('.mode-button');

modeButtons.forEach(button => {
    button.addEventListener('click', () => {
        // Remove 'selected' class from all buttons
        modeButtons.forEach(btn => btn.classList.remove('selected'));
        // Add 'selected' class to the clicked button
        button.classList.add('selected');
        // Get the mode from data attribute
        const mode = button.getAttribute('data-mode');
        // Send the mode command
        const command = { [COMMAND_MODE]: mode };
        ws.send(JSON.stringify(command));
    });
});

// Set default selected mode
document.getElementById('mode-locked').classList.add('selected');

// Sampling and sending commands every 200ms
setInterval(() => {
    // Left joystick throttle command
    if (leftJoystick.isMoving) {
        const throttleCommand = { [COMMAND_THROTTLE]: leftJoystick.verticalValue };
        ws.send(JSON.stringify(throttleCommand));
    }

    // Right joystick direction command
    if (rightJoystick.isMoving) {
        const directionCommand = {
            [COMMAND_DIR_X]: rightJoystick.horizontalValue,
            [COMMAND_DIR_Y]: rightJoystick.verticalValue
        };
        ws.send(JSON.stringify(directionCommand));
    }

    // Right joystick dial rotation command
    if (rightDial.isMoving) {
        const rotationCommand = { [COMMAND_DIR_ROT]: Math.round(rightDial.rotationValue) };
        ws.send(JSON.stringify(rotationCommand));
    }
}, 200);

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
