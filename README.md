# StargneBrows

Simple web browser build from scratch in python, with help of this amazing web book: [browser.engineering](https://browser.engineering/)

## Used libraries

Librarues used by StrangeBrows:

-   [pysdl2](https://pypi.org/project/PySDL2/) - for handling windows
-   [skia-python](https://kyamagu.github.io/skia-python/) - for handling graphical surfaces
-   [DukPy](https://github.com/amol-/dukpy) - for JavaScript execution

Required packages are saved in [requirements.txt](./requirements.txt) and you can download them with:

```bash
pip install -r requraments.txt
```

## Development

For development start project with:

```bash
python ./src/main.py
```

## Build

For building project uses [pyinstaller](https://pyinstaller.org/en/stable/)

To build execute:

```bash
pyinstaller main.spec
```

To run built project execute:

```bash
./dist/main
```

## Testing with server

Project comes with very simple python server for testing. To run test server execute:

```bash
python ./src/server.py
```

You can connect to this server on `https://localhost:8000/`

### Credentials for dummy accounts stored in server:

-   login: `crashoverride`; password: `0cool`
-   login: `cerealkiller`; password: `emmanuel`
