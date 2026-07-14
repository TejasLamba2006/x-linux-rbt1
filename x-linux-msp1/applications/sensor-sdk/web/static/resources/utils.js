/*
 *****************************************************************************
 * @file   utils.js
 * @author SRA-SAIL, Noida
 * @brief  JS Module, collection of utility functions
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

const GenerateUUID = () =>
  ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, c =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)
  );

class Utils {
  static getUUID() {
    return GenerateUUID();
  }
}

export default Utils;
