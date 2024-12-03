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
    lastVerticalValue: 0,
    isMoving: false,
    movementTimeout: null,
};

// Left joystick events
leftJoystick.c1.addEventListener('touchstart', handleLeftJoystickStart, false);
leftJoystick.c1.addEventListener('touchmove', handleLeftJoystickMove, false);
leftJoystick.c1.addEventListener('touchend', handleLeftJoystickEnd, false);

function handleLeftJoystickStart(event) {
    event.preventDefault();
    leftJoystick.isMoving = true;
    clearTimeout(leftJoystick.movementTimeout);
}

function handleLeftJoystickMove(event) {
    event.preventDefault();
    let touch = event.touches[0];
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
    leftJoystick.verticalValue = 0;
    leftJoystick.c1.style.transform = `translateY(0px)`;

    leftJoystick.isMoving = false;
}

// Right Joystick (Thumb)
let rightJoystick = {
    element: document.querySelector('#right-joystick .joystick-inner'),
    c1: document.querySelector('#right-joystick .joystick-inner .c1'),
    maxMovement: 80,
    horizontalValue: 0,
    verticalValue: 0,
    lastHorizontalValue: 0,
    lastVerticalValue: 0,
    isMoving: false,
    movementTimeout: null,
};

// Right joystick events
rightJoystick.c1.addEventListener('touchstart', handleRightJoystickStart, false);
rightJoystick.c1.addEventListener('touchmove', handleRightJoystickMove, false);
rightJoystick.c1.addEventListener('touchend', handleRightJoystickEnd, false);

function handleRightJoystickStart(event) {
    event.preventDefault();
    rightJoystick.isMoving = true;
    clearTimeout(rightJoystick.movementTimeout);
}

function handleRightJoystickMove(event) {
    event.preventDefault();
    let touch = event.touches[0];
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
    rightJoystick.horizontalValue = 0;
    rightJoystick.verticalValue = 0;
    rightJoystick.c1.style.transform = `translate(0px, 0px)`;

    rightJoystick.isMoving = false;
}

// Right Joystick Dial Rotation
let rightDial = {
    element: document.querySelector('#right-joystick .c5'),
    rotationValue: 0,
    lastRotationValue: 0,
    isRotating: false,
    isMoving: false,
    movementTimeout: null,
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
    rightDial.isRotating = true;
    rightDial.isMoving = true;
    clearTimeout(rightDial.movementTimeout);

    const touch = event.touches[0];
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
    const touch = event.touches[0];
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
    rightDial.isRotating = false;
    rightDial.isMoving = false;
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