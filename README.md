
# I2C BUS ERROR ANALYZER

A High Level Analyzer extension for Saleae Logic 2 that detects I2C bus errors. It flags conditions where SDA changes while SCL is high, indicating premature or interrupted transactions such as unexpected starts, stops, or missing data phases.

## Detected errors

- **Unexpected STOP** — STOP condition with no active transaction (spurious SDA rise while SCL high)
- **Empty transaction** — START immediately followed by STOP with no address or data
- **Transaction abort** — START received during an addressed transaction before any data was transferred
- **Repeated START with no address** — back-to-back START conditions
- **Data outside transaction** — data or address bytes appearing without a preceding START
- **Low-level I2C errors** — error frames from the underlying I2C analyzer (SDA changed while SCL high)

## Settings

| Setting   | Options                                     | Description                                      |
|-----------|---------------------------------------------|--------------------------------------------------|
| Display   | Errors only / Errors and warnings / All frames | Controls verbosity of the output frames       |

## Getting started

1. In Logic 2, load the extension from this directory
2. Add the built-in **I2C** analyzer on your SDA/SCL channels
3. Add **I2C BUS ERROR ANALYZER** as a High Level Analyzer, selecting the I2C analyzer as input
4. Run a capture — bus errors will appear as annotated frames on the timeline

