/*
 *****************************************************************************
 * @file   sensordata.js
 * @author SRA-SAIL, Noida
 * @brief  JS Module to calculate pitch and roll from accelerometer data
 *****************************************************************************
 * @attention
 *
 * Copyright (c) 2024 STMicroelectronics.
 * All rights reserved.
 *
 * This software is licensed under terms that can be found in the LICENSE file
 * in the root directory of this software component.
 * If no LICENSE file comes with this software, it is provided AS-IS.
 *
 *****************************************************************************
 */


function getAngle(accX, accY, accZ) {
    //Added 0.0001 to prevent G-Lock
    let pitchRat = accX / Math.sqrt(accY * accY + accZ * accZ + 0.0001);
    let pitch = Math.atan(pitchRat);

    let rollRat = accY / Math.sqrt(accZ* accZ + accY * accY + 0.0001);
    let roll = Math.atan(rollRat);

    let yaw = 0;
    return [pitch, roll, 0];
}


function testData(accX, accY, accZ) {
    var [pitch, roll] = getAngle(accX, accY, accZ);

    console.log(`X = ${accX}, Y = ${accY}, Z = ${accZ}, pitch = ${pitch}, roll = ${roll}`);
}

export default getAngle;
