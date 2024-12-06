

STM32MP157A/C/D/F-DK2 Pin Mapping
---------------------------------------

SAI2 is shared between the audio codec and the GPIO expansion connector. 
By default, the audio codec is connected via solder bridges SB13, SB14, SB15, and SB16.

SOLDIER BRIDGES
------------------------
<SAI2_SCKA>------SB3------|PI5|------SB14------<Pin 12> 
<SAI2_FSA>-------SB1------|PI7|------SB16------<Pin 35> 
<SAI2_SDA>-------SB2------|PI6|------SB15------<Pin 38> 
<SAI2_SDB>-------SB4------|PF11|-----SB13------<Pin 40> 

LED INDICATORS
------------------------
PA14 PA14 is connected to the green LED LD4. Active Low.
PA13 PA13 is connected to the red LED LD6. Active Low.
PH7 PH7 is connected to the orange LED LD7. Active High. [Cube IDE Examples]
PD11 PD11 is connected to the blue LED LD8. Active High. [Linux Heartbeat LED]

SWITCHES
------------------------
NRST Reset button (B2). Aactive Low.
Wake-up button (B1). Connected to the PONKEYn pin of the STPMIC1, allow to wakeup from any low-power mode.
PA13 USER2 user button (B4)
PA14 USER1 user button (B3


| GPIO Header | GPIO Signal | STM32MP Function      | STM32MP Board GPIO |  RBT Board Func          |
|-------------|-------------|-----------------------|--------------------|--------------------------|
| 1           | 3V3         |                       |                    |                          |
| 2           | 5V          |                       |                    |                          |
| 3           | EXP_GPIO2   | I2C5_SDA              | PA12               |  I2C5_SDA                |
| 4           | 5V          |                       |                    |                          |
| 5           | EXP_GPIO3   | I2C5_SCL              | PA11               |  I2C5_SCL                |
| 6           | GND         |                       |                    |                          |
| 7           | EXP_GPIO4   | MCO1                  | PA8                |  IIS2MDC_INT_DRDY        |
| 8           | EXP_GPIO14  | USART3_TX             | PB10               |  ISM330DHC_INT1          |
| 9           | GND         |                       |                    |                          |
| 10          | EXP_GPIO15  | USART3_RX             | PB12               |  ISM330DHC_INT2          |
| 11          | EXP_GPIO17  | USART3_RTS            | PG8                |  LPS22HH_INT_DRDY        |
| 12          | EXP_GPIO18  | SAI2_SCKA             | PI5                |  GPIO_LED2       |
| 13          | EXP_GPIO27  | SDMMC3_D3             | PD7                |  STSPIN948_1_ENA_nFAULTA |
| 14          | GND         |                       |                    |                          |
| 15          | EXP_GPIO22  | SDMMC3_CK             | PG15               |  STSPIN948_1_ENA_nFAULTB |
| 16          | EXP_GPIO23  | SDMMC3_CMD            | PF1                |  STSPIN948_2_ENA_nFAULTA |
| 17          | 3V3         |                       |                    |                          |
| 18          | EXP_GPIO24  | SDMMC3_D0             | PF0                |  STSPIN948_2_ENA_nFAULTB |
| 19          | EXP_GPIO10  | SPI5_MOSI             | PF9                |  STSPIN948_2_GPIOA       |
| 20          | GND         |                       |                    |                          |
| 21          | EXP_GPIO9   | SPI5_MISO             | PF8                |  STSPIN948_2_GPIOB       |
| 22          | EXP_GPIO25  | SDMMC3_D1             | PF4                |  GPIO_LED5               |
| 23          | EXP_GPIO11  | SPI5_SCK              | PF7                |  STSPIN948_1_GPIOA       |
| 24          | EXP_GPIO8   | SPI5_NSS              | PF6                |  STSPIN948_1_GPIOB       |
| 25          | GND         |                       |                    |                          |
| 26          | EXP_GPIO7   | GPIO_STMOD_RI         | PF3                |  GPIO_LED4               |
| 27          | ID_SD       | I2C1_SDA              | PF15               |  EEPROM_ID_SD            |
| 28          | ID_SC       | I2C1_SCL              | PD12               |  EEPROM_ID_SC            |
| 29          | EXP_GPIO5   | MCO2                  | PG2                |  GPIO_LED3               |
| 30          | GND         |                       |                    |                          |
| 31          | EXP_GPIO6   | TIM5_CH2              | PH11               |  STSPIN948_2_PWM1A       |
| 32          | EXP_GPIO12  | TIM4_CH2              | PD13               |  STSPIN948_1_PWM1A       |
| 33          | EXP_GPIO13  | TIM3_CH2              | PC7                |  STSPIN948_1_PWM1B       |
| 34          | GND         |                       |                    |                          |
| 35          | EXP_GPIO19  | SAI2_FSA              | PI7                |  VL53L5CX_INT            |
| 36          | EXP_GPIO16  | USART3_CTS            | PB13               |  STSPIN948_2_PWM1B               |
| 37          | EXP_GPIO26  | SDMMC3_D2             | PF5                |  GPIO_LED1               |
| 38          | EXP_GPIO20  | SAI2_SDA              | PI6                |  VL53L5CX_I2C_RST        |
| 39          | GND         |                       |                    |                          |
| 40          | EXP_GPIO21  | SAI2_SDB              | PF11               |  VL53L5CX_LPn_GPIO_SW    |
-----------------------------------------------------------------------------------------------------


    Hexa Conversion Table
    ---------------------
    0   1   2   3   4   5   6   7   8   9
    A   B   C   D   E   F   G   H   I   J



STM32MP257F-DK Pin Mapping
---------------------------------------


