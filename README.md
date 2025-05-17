# Workbench

Test and measurement code for my bench.

## Features

- **Supported Instruments**:
  - Keysight 34461A
  - Keysight DAQ970A
  - Keysight E36105B
  - Keysight DSOX1204G
  - Agilent U2751A
  - Brymen BM869S
  - Fluke 2620A
  - Siglent SDG1022X+
  - Digilent Analog Discovery 3

- **Data Analysis Utilities**:
  - Uncertainty calculation
  - Measurement formatting and unit handling
  - Time series analysis with InfluxDB integration

## Installation

Workbench uses Poetry for dependency management. To install:

```bash
# Clone the repository
git clone git@github.com:unusual-audio/workbench.git
cd workbench

poetry install
poetry run python
```

## Usage Examples

### Connecting to an Instrument

```python
from workbench.instruments.keysight_34461a import Keysight34461A

# Connect to the instrument
with Keysight34461A.connect("USB0::0x2A8D::0x0101::MY12345678::INSTR") as dmm:
    dmm.display_text = "Hello, World!"
```

### Uncertainty Analysis

```python
import numpy as np
from workbench.utils import get_type_a_uncertainty, get_type_b_uncertainty, get_expanded_uncertainty

# Load measurement data
measurements = np.array([5.0001, 5.0003, 5.0002, 5.0001, 5.0004])

# Calculate Type A uncertainty (statistical)
type_a = get_type_a_uncertainty(measurements)

# Calculate Type B uncertainty (systematic, based on instrument specifications)
# For example, for a Keysight 34461A on 10V range: ±(50 ppm of reading + 5 ppm of range)
expanded_type_b = abs(measurements) * 50e-6 + 10 * 5e-6
type_b = get_type_b_uncertainty(expanded_type_b, k=2)

# Calculate expanded uncertainty (k=2 for 95% confidence)
expanded_uncertainty = get_expanded_uncertainty(type_a, type_b, k=2)

print(f"Measurement: {np.mean(measurements):.7f} ± {expanded_uncertainty:.7f} V (k=2)")
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

Unusual Audio <unusualaudio@protonmail.com>
