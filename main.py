import os
import uuid
import shutil

PER_MB = 1024 * 1024
MB_SIZE = 60
PER_READ_SIZE = 1024
PART_FILE_SUFFIX = ".fsp"


def int_to_bytes(n):
    pos = n >= 0
    if not pos:
        n = -n
    bytes_array = bytearray(5)
    bytes_array[4] = n & 0xff
    n = n >> 8
    bytes_array[3] = n & 0xff
    n = n >> 8
    bytes_array[2] = n & 0xff
    n = n >> 8
    bytes_array[1] = n & 0xff
    bytes_array[0] = 0 if pos else 1
    return bytes_array


def bytes_to_int(byte_array):
    n = 0
    n = byte_array[1] & 0xff
    n = (n << 8) | (byte_array[2] & 0xff)
    n = (n << 8) | (byte_array[3] & 0xff)
    n = (n << 8) | (byte_array[4] & 0xff)
    if byte_array[0] == 1:
        n = -n
    return n


def get_all_files(input_file):
    all_files = {}
    if os.path.isfile(input_file):
        return get_all_files_with_prefix(None, input_file)
    if os.path.isdir(input_file):
        for entry in os.listdir(input_file):
            sub_files = get_all_files_with_prefix(None, os.path.join(input_file, entry))
            all_files.update(sub_files)

    return all_files


def file_name_escape(file_name):
    return file_name.replace("/", "\\/")


def to_hierarchy_names(escape_file_name):
    result = []
    sb = []
    for char in escape_file_name:
        if char == '\\':
            if escape_file_name.index(char) < len(escape_file_name) - 1 and escape_file_name[escape_file_name.index(char) + 1] == '/':
                sb.append('/')
                continue
        if char == '/':
            result.append(''.join(sb))
            sb = []
            continue
        sb.append(char)
    if len(sb) > 0:
        result.append(''.join(sb))
    return result


def get_all_files_with_prefix(prefix, input_file):
    all_files = {}
    if os.path.isfile(input_file):
        file_name = file_name_escape(os.path.basename(input_file))
        key = os.path.join(prefix, file_name) if prefix is not None else file_name
        all_files[key] = input_file
        return all_files
    if os.path.isdir(input_file):
        file_name = file_name_escape(os.path.basename(input_file))
        prefix = os.path.join(prefix, file_name) if prefix is not None else file_name

        for entry in os.listdir(input_file):
            sub_files = get_all_files_with_prefix(prefix, os.path.join(input_file, entry))
            all_files.update(sub_files)

    return all_files


def package_file(input_dir, output_dir):
    user_base_dir = os.getcwd()

    input_file = os.path.join(user_base_dir, input_dir) if not input_dir.startswith('/') else input_dir
    output_file = os.path.join(user_base_dir, output_dir) if not output_dir.startswith('/') else output_dir

    if os.path.isdir(input_file):
        file_base = input_file
    else:
        file_base = os.path.dirname(input_file)

    all_files = get_all_files(input_file)

    for file_key, value in all_files.items():
        file_key_bytes = file_key.encode('utf-8')

        print(f"file {os.path.abspath(value)}")
        with open(value, "rb") as fis:
            length = os.path.getsize(value)
            mb = length // PER_MB + (0 if length % PER_MB == 0 else 1)
            file_count = mb // MB_SIZE + (0 if mb % MB_SIZE == 0 else 1)
            if file_count == 0:
                file_count = 1
            per_file_size = length // file_count + (0 if length % file_count == 0 else 1)

            print(f"perFileSize {per_file_size} fileCount {file_count} available {length}")
            for file_index in range(file_count):
                file_name = str(uuid.uuid4()) + PART_FILE_SUFFIX
                file_path = os.path.join(output_file, file_name)

                print(f"create file {file_name}")
                open(file_path, 'wb').close()

                seq_bytes = int_to_bytes(file_index + 1)
                head_size = len(seq_bytes) + len(file_key_bytes) + 5
                head_bytes = int_to_bytes(head_size)

                with open(file_path, 'ab') as fos:
                    # 文件头
                    fos.write(head_bytes)
                    # 子文件序号
                    fos.write(seq_bytes)
                    # 文件名
                    fos.write(file_key_bytes)

                    part_size = min(length - file_index * per_file_size, per_file_size)
                    bytes_array = bytearray(PER_READ_SIZE)
                    read_size = 0

                    while read_size < part_size:
                        read = fis.readinto(bytes_array)
                        if read == 0:
                            break
                        read_size += read
                        # 文件内容
                        fos.write(bytes_array[:read])


def read_part_files(input_file):
    file_map = {}
    if os.path.isdir(input_file):
        files = [f for f in os.listdir(input_file) if os.path.isfile(os.path.join(input_file, f))]
        for file_name in files:
            if not file_name.endswith(PART_FILE_SUFFIX):
                continue
            with open(os.path.join(input_file, file_name), 'rb') as fis:
                head_bytes = fis.read(5)
                if len(head_bytes) < 5:
                    continue

                head_count = bytes_to_int(head_bytes)

                seq_bytes = fis.read(5)
                if len(seq_bytes) < 5:
                    continue
                part = bytes_to_int(seq_bytes)
                if head_count - 10 > 3000:
                    continue
                name_bytes = fis.read(head_count - 10)
                if len(name_bytes) < head_count - 10:
                    continue

                file_key = name_bytes.decode('utf-8')
                file_map[file_key] = file_map.get(file_key, []) + [{"part": part, "file_name": file_key, "file": file_name}]

    return file_map


def unpackage_file(input_dir, output_dir):
    user_base_dir = os.getcwd()

    input_file = os.path.join(user_base_dir, input_dir) if not input_dir.startswith('/') else input_dir
    output_file = os.path.join(user_base_dir, output_dir) if not output_dir.startswith('/') else output_dir

    if not os.path.isdir(input_file):
        raise Exception("file is not a directory")

    part_file_map = read_part_files(input_file)

    for file_key, part_file_infos in part_file_map.items():
        part_file_infos.sort(key=lambda x: x['part'])

        print(f"restore {file_key}")

        hierarchy_names = to_hierarchy_names(file_key)
        file = output_file
        for i in range(len(hierarchy_names)):
            hierarchy_name = hierarchy_names[i]
            file = os.path.join(file, hierarchy_name)
            if i < len(hierarchy_names) - 1:
                if not os.path.exists(file):
                    os.mkdir(file)
                    print(f"mkdir {os.path.abspath(file)}")
            else:
                if os.path.exists(file):
                    os.remove(file)
                open(file, 'wb').close()
                print(f"create file {os.path.abspath(file)}")

        for part_file_info in part_file_infos:
            part_file = part_file_info['file']
            with open(os.path.join(input_file, part_file), 'rb') as part_fis:
                head_bytes = part_fis.read(5)
                head_size = bytes_to_int(head_bytes)

                part_fis.read(head_size - 5)

                bytes_array = bytearray(1024)
                with open(file, 'ab') as fos:
                    while True:
                        read = part_fis.readinto(bytes_array)
                        if read == 0:
                            break
                        fos.write(bytes_array[:read])


if __name__ == '__main__':
    import sys

    print(sys.argv)
    if len(sys.argv) < 4:
        print("please input mode, input dir and output dir")
    elif sys.argv[1] == "1":
        package_file(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "2":
        unpackage_file(sys.argv[2], sys.argv[3])
    else:
        print("mode must be 1 or 2")