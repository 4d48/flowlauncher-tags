# AI generated


import base64
import ctypes
import io

from PIL import Image

# Load system libraries for Win32 API operations
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# --- TYPE DEFINITIONS FOR X64 COMPATIBILITY ---
HICON = ctypes.c_void_p
HBITMAP = ctypes.c_void_p
HDC = ctypes.c_void_p
HANDLE = ctypes.c_void_p

user32.PrivateExtractIconsW.argtypes = [
    ctypes.c_wchar_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(HICON),
    ctypes.POINTER(ctypes.c_uint),
    ctypes.c_uint,
    ctypes.c_uint,
]
user32.PrivateExtractIconsW.restype = ctypes.c_uint

user32.GetIconInfo.argtypes = [HICON, ctypes.c_void_p]
user32.GetIconInfo.restype = ctypes.c_bool

user32.GetDC.argtypes = [ctypes.c_void_p]
user32.GetDC.restype = HDC

user32.ReleaseDC.argtypes = [ctypes.c_void_p, HDC]
user32.ReleaseDC.restype = ctypes.c_int

user32.DestroyIcon.argtypes = [HICON]
user32.DestroyIcon.restype = ctypes.c_bool

gdi32.GetObjectW.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p]
gdi32.GetObjectW.restype = ctypes.c_int

gdi32.GetDIBits.argtypes = [
    HDC,
    HBITMAP,
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint,
]
gdi32.GetDIBits.restype = ctypes.c_int

gdi32.DeleteObject.argtypes = [HANDLE]
gdi32.DeleteObject.restype = ctypes.c_bool
# -----------------------------------------------


def extract_dll_icon_as_image(
    dll_path: str, icon_index: int, icon_size: int = 48
) -> Image.Image:
    """
    Extracts an icon from a DLL by index and returns it as a PIL Image object.
    """
    phicon = (HICON * 1)()
    piconid = (ctypes.c_uint * 1)()

    result = user32.PrivateExtractIconsW(
        dll_path,
        icon_index,
        icon_size,
        icon_size,
        phicon,
        piconid,
        1,
        0,
    )

    if result == 0 or not phicon[0]:
        raise FileNotFoundError(
            f"Failed to extract icon at index {icon_index} from {dll_path}"
        )

    hicon = phicon[0]

    try:

        class ICONINFO(ctypes.Structure):
            _fields_ = [
                ("fIcon", ctypes.c_bool),
                ("xHotspot", ctypes.c_uint),
                ("yHotspot", ctypes.c_uint),
                ("hbmMask", HBITMAP),
                ("hbmColor", HBITMAP),
            ]

        icon_info = ICONINFO()
        user32.GetIconInfo(hicon, ctypes.byref(icon_info))

        class BITMAP(ctypes.Structure):
            _fields_ = [
                ("bmType", ctypes.c_long),
                ("bmWidth", ctypes.c_long),
                ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long),
                ("bmPlanes", ctypes.c_ushort),
                ("bmBitsPixel", ctypes.c_ushort),
                ("bmBits", ctypes.c_void_p),
            ]

        bmp = BITMAP()
        gdi32.GetObjectW(icon_info.hbmColor, ctypes.sizeof(bmp), ctypes.byref(bmp))

        hdc = user32.GetDC(None)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", ctypes.c_ushort),
                ("biBitCount", ctypes.c_ushort),
                ("biCompression", ctypes.c_uint),
                ("biSizeImage", ctypes.c_uint),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", ctypes.c_uint),
                ("biClrImportant", ctypes.c_uint),
            ]

        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = bmp.bmWidth
        bi.biHeight = -bmp.bmHeight  # Top-Down
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0  # BI_RGB

        buffer_size = bmp.bmWidth * bmp.bmHeight * 4
        pixel_buffer = ctypes.create_string_buffer(buffer_size)

        gdi32.GetDIBits(
            hdc, icon_info.hbmColor, 0, bmp.bmHeight, pixel_buffer, ctypes.byref(bi), 0
        )

        user32.ReleaseDC(None, hdc)
        gdi32.DeleteObject(icon_info.hbmColor)
        gdi32.DeleteObject(icon_info.hbmMask)

        return Image.frombytes(
            "RGBA", (bmp.bmWidth, bmp.bmHeight), pixel_buffer.raw, "raw", "BGRA"
        )

    finally:
        user32.DestroyIcon(hicon)


def save_dll_icon_to_png(
    dll_path: str, icon_index: int, output_file_path: str, icon_size: int = 48
) -> None:
    """
    Extracts an icon from a DLL and saves it directly to a PNG file.
    """
    img = extract_dll_icon_as_image(dll_path, icon_index, icon_size)
    img.save(output_file_path, format="PNG")


def get_dll_icon_as_data_uri(
    dll_path: str, icon_index: int, icon_size: int = 48
) -> str:
    """
    Extracts an icon from a DLL by index and returns it in Data URI format (Base64).
    """
    img = extract_dll_icon_as_image(dll_path, icon_index, icon_size)
    output = io.BytesIO()
    img.save(output, format="PNG")
    png_bytes = output.getvalue()

    base64_data = base64.b64encode(png_bytes).decode("utf-8")
    return f"data:image/png;base64,{base64_data}"


# --- Usage Example ---
if __name__ == "__main__":
    dll = "C:\\Windows\\System32\\imageres.dll"

    try:
        # Save the icon directly to a PNG file
        png_path = "icon_14.png"
        save_dll_icon_to_png(
            dll, icon_index=14, output_file_path=png_path, icon_size=48
        )
        print(f"Icon successfully saved to file: {png_path}")

        # Get Data URI
        data_uri = get_dll_icon_as_data_uri(dll, icon_index=14, icon_size=48)
        print("Generated Data URI (first 100 characters):")
        print(data_uri[:100] + "...")
    except Exception as e:
        print(f"Error: {e}")
