#!/bin/sh

# I2C bus number
I2C_BUS=1

# I2C address of ISM330DHCX
I2C_ADDRESS=0x6B

# Register addresses
WHO_AM_I_REG=0x0F
CTRL1_XL_REG=0x10
OUTX_L_A=0x28
OUTX_H_A=0x29
OUTY_L_A=0x2A
OUTY_H_A=0x2B
OUTZ_L_A=0x2C
OUTZ_H_A=0x2D

# Scale ±2g
FULL_SCALE=2000
MAX_VAL=32768


# Initialize the accelerometer: ODR = 104 Hz, Full-scale = ±2g
# 0x60 corresponds to 104 Hz and ±2g in CTRL1_XL (0b01100000)
i2cset -y $I2C_BUS $I2C_ADDRESS $CTRL1_XL_REG 0x40

# Read WHO_AM_I register
who_am_i=$(i2cget -y $I2C_BUS $I2C_ADDRESS $WHO_AM_I_REG)
echo "WHO_AM_I register: $who_am_i"

# Read accelerometer X-axis
outx_l_a=$(i2cget -y $I2C_BUS $I2C_ADDRESS $OUTX_L_A)
outx_h_a=$(i2cget -y $I2C_BUS $I2C_ADDRESS $OUTX_H_A)
x_accel_raw=$(( (outx_h_a << 8) | outx_l_a ))

# Read accelerometer Y-axis
outy_l_a=$(i2cget -y $I2C_BUS $I2C_ADDRESS $OUTY_L_A)
outy_h_a=$(i2cget -y $I2C_BUS $I2C_ADDRESS $OUTY_H_A)
y_accel_raw=$(( (outy_h_a << 8) | outy_l_a ))

# Read accelerometer Z-axis
outz_l_a=$(i2cget -y $I2C_BUS $I2C_ADDRESS $OUTZ_L_A)
outz_h_a=$(i2cget -y $I2C_BUS $I2C_ADDRESS $OUTZ_H_A)
z_accel_raw=$(( (outz_h_a << 8) | outz_l_a ))

# Convert to signed 16-bit integers if necessary
if [ $x_accel_raw -ge 32768 ]; then
  x_accel_raw=$((x_accel_raw - 65536))
fi

if [ $y_accel_raw -ge 32768 ]; then
  y_accel_raw=$((y_accel_raw - 65536))
fi

if [ $z_accel_raw -ge 32768 ]; then
  z_accel_raw=$((z_accel_raw - 65536))
fi

# Apply scale to get values in milli-g (mg)
x_accel_mg=$((x_accel_raw * FULL_SCALE / MAX_VAL))
y_accel_mg=$((y_accel_raw * FULL_SCALE / MAX_VAL))
z_accel_mg=$((z_accel_raw * FULL_SCALE / MAX_VAL))

echo "X-axis acceleration: $x_accel_mg mg"
echo "Y-axis acceleration: $y_accel_mg mg"
echo "Z-axis acceleration: $z_accel_mg mg"
