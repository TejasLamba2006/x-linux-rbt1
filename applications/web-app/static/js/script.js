// application/web-app/static/js/script.js

// Establish WebSocket connection
let ws = new WebSocket('ws://' + window.location.host + '/ws');

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
    maxMovement: 80, // Doubled from 40
    verticalValue: 0,
};

// Left joystick events
leftJoystick.c1.addEventListener('touchstart', handleLeftJoystickStart, false);
leftJoystick.c1.addEventListener('touchmove', handleLeftJoystickMove, false);
leftJoystick.c1.addEventListener('touchend', handleLeftJoystickEnd, false);

function handleLeftJoystickStart(event) {
    event.preventDefault();
}

function handleLeftJoystickMove(event) {
    event.preventDefault();
    let touch = event.touches[0];
    let rect = leftJoystick.element.getBoundingClientRect();
    let y = touch.clientY - rect.top - rect.height / 2;
    y = Math.max(-leftJoystick.maxMovement, Math.min(leftJoystick.maxMovement, y));
    leftJoystick.verticalValue = -Math.round((y / leftJoystick.maxMovement) * 100);
    leftJoystick.c1.style.transform = `translateY(${y}px)`;
}

function handleLeftJoystickEnd(event) {
    event.preventDefault();
    leftJoystick.verticalValue = 0;
    leftJoystick.c1.style.transform = `translateY(0px)`;
}

// Right Joystick (Thumb)
let rightJoystick = {
    element: document.querySelector('#right-joystick .joystick-inner'),
    c1: document.querySelector('#right-joystick .joystick-inner .c1'),
    maxMovement: 80, // Doubled from 40
    horizontalValue: 0,
    verticalValue: 0,
};

// Right joystick events
rightJoystick.c1.addEventListener('touchstart', handleRightJoystickStart, false);
rightJoystick.c1.addEventListener('touchmove', handleRightJoystickMove, false);
rightJoystick.c1.addEventListener('touchend', handleRightJoystickEnd, false);

function handleRightJoystickStart(event) {
    event.preventDefault();
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
}

function handleRightJoystickEnd(event) {
    event.preventDefault();
    rightJoystick.horizontalValue = 0;
    rightJoystick.verticalValue = 0;
    rightJoystick.c1.style.transform = `translate(0px, 0px)`;
}

// Right Joystick Dial Rotation
let rightDial = {
    element: document.querySelector('#right-joystick .c5'),
    rotationValue: 0,
    isRotating: false,
    startAngle: 0,
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
}

function handleDialEnd(event) {
    event.preventDefault();
    rightDial.isRotating = false;
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
        const command = { "mode": mode };
        ws.send(JSON.stringify(command));
    });
});

// Set default selected mode
document.getElementById('mode-locked').classList.add('selected');

// Sampling and sending commands every 200ms
setInterval(() => {
    // Left joystick throttle command
    const throttleCommand = { "throttle": leftJoystick.verticalValue };
    ws.send(JSON.stringify(throttleCommand));

    // Right joystick direction command
    const directionCommand = {
        "dir_x": rightJoystick.horizontalValue,
        "dir_y": rightJoystick.verticalValue
    };
    ws.send(JSON.stringify(directionCommand));

    // Right joystick dial rotation command
    const rotationCommand = { "dir_rot": Math.round(rightDial.rotationValue) };
    ws.send(JSON.stringify(rotationCommand));
}, 200);

