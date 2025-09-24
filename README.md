# StargneBrows

Simple web browser build from scratch in python, with help of this amazing web book: [browser.engineering](https://browser.engineering/)

## Used libraries

To run StrangeBrows you will need:

-   [tkinter](https://docs.python.org/3/library/tkinter.html) - for creating windows

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
