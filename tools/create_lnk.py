"""
Create Windows .lnk shortcut files with console settings.

Uses win32com for basic .lnk creation, then manually modifies ConsoleDataBlock
for settings not exposed by the COM interface.

Based on MS-SHLLINK specification:
https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-shllink/
"""

import struct
from pathlib import Path
import win32com.client


class LnkCreator:
    """Creates Windows .lnk shortcut files with console configuration."""

    # ConsoleDataBlock constants (from MS-SHLLINK spec)
    CONSOLE_BLOCK_SIGNATURE = 0xA0000002
    CONSOLE_BLOCK_SIZE = 0x000000CC  # 204 bytes
    HEADER_SIZE = 0x0000004C  # 76 bytes

    # LinkFlags
    HasLinkTargetIDList = 0x00000001
    HasLinkInfo = 0x00000002
    HasName = 0x00000004
    HasRelativePath = 0x00000008
    HasWorkingDir = 0x00000010
    HasArguments = 0x00000020
    HasIconLocation = 0x00000040
    IsUnicode = 0x00000080

    def __init__(self, target, output_file, working_dir=None, icon_path=None, icon_index=0,
                 arguments=None, description=None, quickedit=False, buffer_size=(120, 9001),
                 window_size=(120, 30)):
        """
        Initialize LnkCreator.

        Args:
            target: Path to the target executable
            output_file: Path where the .lnk file will be created
            working_dir: Working directory (starting path)
            icon_path: Path to icon file
            icon_index: Icon index within icon file
            arguments: Command line arguments
            description: Shortcut description
            quickedit: Enable QuickEdit mode
            buffer_size: Console buffer size as (width, height) tuple
            window_size: Console window size as (width, height) tuple
        """
        self.target = str(Path(target).resolve())
        self.output_file = Path(output_file).resolve()
        self.working_dir = str(Path(working_dir).resolve()) if working_dir else None
        self.icon_location = str(Path(icon_path).resolve()) if icon_path else None
        self.icon_index = icon_index
        self.arguments = arguments
        self.description = description

        # Console settings (not available via COM)
        self.quickedit_enabled = quickedit
        self.buffer_size = buffer_size
        self.window_size = window_size
        self.screen_colors = 0x0007      # White on black
        self.popup_colors = 0x00F5       # Purple on white
        self.font_size = 0x00100000      # 16pt font (Windows default)
        self.cursor_size = 25
        self.history_buffer_size = 50
        self.num_history_buffers = 4

    def _create_basic_lnk(self):
        """Create basic .lnk file using win32com."""
        shell = win32com.client.Dispatch('WScript.Shell')
        shortcut = shell.CreateShortcut(str(self.output_file))

        shortcut.TargetPath = self.target

        if self.working_dir:
            shortcut.WorkingDirectory = self.working_dir

        if self.icon_location:
            shortcut.IconLocation = f"{self.icon_location}, {self.icon_index}"

        if self.arguments:
            shortcut.Arguments = self.arguments

        if self.description:
            shortcut.Description = self.description

        shortcut.Save()
        del shortcut
        del shell

    def _build_console_data_block(self):
        """Build ConsoleDataBlock (204 bytes)."""
        data = bytearray()

        # BlockSize (4 bytes)
        data += struct.pack('<I', 0x000000CC)

        # BlockSignature (4 bytes)
        data += struct.pack('<I', 0xA0000002)

        # FillAttributes (2 bytes)
        data += struct.pack('<H', self.screen_colors)

        # PopupFillAttributes (2 bytes)
        data += struct.pack('<H', self.popup_colors)

        # ScreenBufferSizeX, ScreenBufferSizeY (2 bytes each)
        data += struct.pack('<hh', self.buffer_size[0], self.buffer_size[1])

        # WindowSizeX, WindowSizeY (2 bytes each)
        data += struct.pack('<hh', self.window_size[0], self.window_size[1])

        # WindowOriginX, WindowOriginY (2 bytes each)
        data += struct.pack('<hh', 0, 0)

        # Unused1, Unused2 (4 bytes each)
        data += struct.pack('<II', 0, 0)

        # FontSize (4 bytes)
        data += struct.pack('<I', self.font_size)

        # FontFamily (4 bytes) - 0x0036 = FF_MODERN | TMPF_FIXED_PITCH
        data += struct.pack('<I', 0x00000036)

        # FontWeight (4 bytes) - 400 = normal
        data += struct.pack('<I', 400)

        # FaceName (64 bytes) - "Consolas" as Unicode
        face_name = "Consolas".encode('utf-16-le')
        face_name += b'\x00' * (64 - len(face_name))  # Pad to 64 bytes
        data += face_name

        # CursorSize (4 bytes) - 25 = default
        data += struct.pack('<I', 25)

        # FullScreen (4 bytes) - 0 = windowed mode
        data += struct.pack('<I', 0)

        # QuickEdit (4 bytes) - THIS IS THE KEY FIELD at offset 0x74
        data += struct.pack('<I', 1 if self.quickedit_enabled else 0)

        # InsertMode (4 bytes) - 1 = enabled
        data += struct.pack('<I', 1)

        # AutoPosition (4 bytes) - 1 = system positions the window
        data += struct.pack('<I', 1)

        # HistoryBufferSize (4 bytes)
        data += struct.pack('<I', 50)

        # NumberOfHistoryBuffers (4 bytes)
        data += struct.pack('<I', 4)

        # HistoryNoDup (4 bytes) - 0 = allow duplicates
        data += struct.pack('<I', 0)

        # ColorTable (64 bytes) - 16 COLORREF values
        # Standard console colors
        color_table = [
            0x00000000,  # Black
            0x00800000,  # Dark Blue
            0x00008000,  # Dark Green
            0x00808000,  # Dark Cyan
            0x00000080,  # Dark Red
            0x00800080,  # Dark Magenta
            0x00008080,  # Dark Yellow
            0x00C0C0C0,  # Gray
            0x00808080,  # Dark Gray
            0x00FF0000,  # Blue
            0x0000FF00,  # Green
            0x00FFFF00,  # Cyan
            0x000000FF,  # Red
            0x00FF00FF,  # Magenta
            0x0000FFFF,  # Yellow
            0x00FFFFFF,  # White
        ]
        for color in color_table:
            data += struct.pack('<I', color)

        return data

    def _find_console_block(self, data, offset):
        """
        Find ConsoleDataBlock in ExtraData section.
        Returns the offset of the block or None if not found.
        """
        while offset < len(data):
            if offset + 8 > len(data):
                break

            block_size = struct.unpack('<I', data[offset:offset+4])[0]

            if block_size < 0x00000004:
                # Terminal block
                break

            block_sig = struct.unpack('<I', data[offset+4:offset+8])[0]

            if block_sig == self.CONSOLE_BLOCK_SIGNATURE:
                return offset

            # Move to next block
            offset += block_size

        return None

    def _skip_to_extra_data(self, data):
        """
        Skip through .lnk structure to find where ExtraData begins.
        Returns the offset where ExtraData starts.
        """
        offset = 0

        # Skip header (76 bytes)
        offset += self.HEADER_SIZE

        # Read LinkFlags to know what sections are present
        link_flags = struct.unpack('<I', data[20:24])[0]

        # Skip LinkTargetIDList if present
        if link_flags & self.HasLinkTargetIDList:
            id_list_size = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2 + id_list_size

        # Skip LinkInfo if present
        if link_flags & self.HasLinkInfo:
            link_info_size = struct.unpack('<I', data[offset:offset+4])[0]
            offset += link_info_size

        # Skip StringData sections
        is_unicode = link_flags & self.IsUnicode

        for flag in [self.HasName, self.HasRelativePath, self.HasWorkingDir,
                     self.HasArguments, self.HasIconLocation]:
            if link_flags & flag:
                count_chars = struct.unpack('<H', data[offset:offset+2])[0]
                offset += 2
                bytes_per_char = 2 if is_unicode else 1
                offset += count_chars * bytes_per_char

        return offset

    def create(self):
        """Create the .lnk file with console settings."""
        # Ensure target exists
        if not Path(self.target).exists():
            raise FileNotFoundError(f"Target does not exist: {self.target}")

        # Ensure output directory exists
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        # Step 1: Create basic .lnk using win32com
        self._create_basic_lnk()

        # Step 2: Read the .lnk file back
        with open(self.output_file, 'rb') as f:
            data = bytearray(f.read())

        # Step 3: Find where ExtraData section starts
        extra_data_offset = self._skip_to_extra_data(data)

        # Step 4: Check if ConsoleDataBlock exists
        console_block_offset = self._find_console_block(data, extra_data_offset)

        # Step 5: Build new ConsoleDataBlock with our settings
        console_block = self._build_console_data_block()

        if console_block_offset is not None:
            # Replace existing ConsoleDataBlock
            data[console_block_offset:console_block_offset + self.CONSOLE_BLOCK_SIZE] = console_block
        else:
            # Add new ConsoleDataBlock before terminal block
            # Find terminal block (4 bytes < 0x00000004)
            terminal_offset = extra_data_offset
            while terminal_offset < len(data):
                if terminal_offset + 4 > len(data):
                    # No terminal block, add one
                    data += console_block
                    data += struct.pack('<I', 0x00000000)  # Terminal
                    break

                block_size = struct.unpack('<I', data[terminal_offset:terminal_offset+4])[0]
                if block_size < 0x00000004:
                    # Found terminal block, insert before it
                    data[terminal_offset:terminal_offset] = console_block
                    break

                terminal_offset += block_size

        # Step 6: Write modified .lnk file
        with open(self.output_file, 'wb') as f:
            f.write(data)

        return self.output_file


def create_lnk(output_file, target, working_dir=None, icon_path=None, icon_index=0,
               quickedit=False, buffer_size=(120, 9001), window_size=(120, 30),
               arguments=None, description=None):
    """
    Create a Windows .lnk shortcut file.

    Args:
        output_file: Where to save the .lnk file
        target: Path to the target executable
        working_dir: Starting directory (optional)
        icon_path: Path to icon file (optional)
        icon_index: Icon index within icon file (default: 0)
        quickedit: Enable QuickEdit mode (default: False)
        buffer_size: Console buffer size as (width, height) tuple
        window_size: Console window size as (width, height) tuple
        arguments: Command line arguments (optional)
        description: Shortcut description (optional)

    Returns:
        Path to the created .lnk file
    """
    creator = LnkCreator(target, output_file, working_dir, icon_path, icon_index,
                         arguments, description, quickedit, buffer_size, window_size)
    return creator.create()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Windows .lnk Shortcut Creator")
        print()
        print("Usage: python lnk_create.py <output.lnk> <target> [options]")
        print()
        print("Options:")
        print("  --working-dir PATH      Set working directory")
        print("  --icon PATH             Set icon location")
        print("  --quickedit on|off      Enable/disable QuickEdit (default: off)")
        print("  --buffer WxH            Buffer size, e.g., 120x9001 (default: 120x9001)")
        print("  --window WxH            Window size, e.g., 120x30 (default: 120x30)")
        print("  --args ARGS             Command line arguments")
        print("  --desc TEXT             Shortcut description")
        print()
        print("Example:")
        print("  python lnk_create.py cmd_test.lnk C:\\Windows\\System32\\cmd.exe \\")
        print("    --working-dir C:\\Users --quickedit off --window 120x30")
        sys.exit(1)

    output = sys.argv[1]
    target = sys.argv[2]

    # Parse options
    working_dir = None
    icon_path = None
    quickedit = False
    buffer_size = (120, 9001)
    window_size = (120, 30)
    arguments = None
    description = None

    i = 3
    while i < len(sys.argv):
        arg = sys.argv[i]

        if arg == '--working-dir' and i + 1 < len(sys.argv):
            working_dir = sys.argv[i + 1]
            i += 2
        elif arg == '--icon' and i + 1 < len(sys.argv):
            icon_path = sys.argv[i + 1]
            i += 2
        elif arg == '--quickedit' and i + 1 < len(sys.argv):
            quickedit = sys.argv[i + 1].lower() in ('on', 'true', '1', 'yes')
            i += 2
        elif arg == '--buffer' and i + 1 < len(sys.argv):
            w, h = sys.argv[i + 1].lower().split('x')
            buffer_size = (int(w), int(h))
            i += 2
        elif arg == '--window' and i + 1 < len(sys.argv):
            w, h = sys.argv[i + 1].lower().split('x')
            window_size = (int(w), int(h))
            i += 2
        elif arg == '--args' and i + 1 < len(sys.argv):
            arguments = sys.argv[i + 1]
            i += 2
        elif arg == '--desc' and i + 1 < len(sys.argv):
            description = sys.argv[i + 1]
            i += 2
        else:
            print(f"Unknown option: {arg}")
            sys.exit(1)

    try:
        result = create_lnk(
            output, target, working_dir, icon_path, 0,
            quickedit, buffer_size, window_size,
            arguments, description
        )

        print(f"Successfully created: {result}")
        print(f"File size: {result.stat().st_size} bytes")
        print(f"Target: {target}")
        if working_dir:
            print(f"Working directory: {working_dir}")
        print(f"QuickEdit: {'ENABLED' if quickedit else 'DISABLED'}")
        print(f"Buffer size: {buffer_size[0]}x{buffer_size[1]}")
        print(f"Window size: {window_size[0]}x{window_size[1]}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
