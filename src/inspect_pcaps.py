
from pathlib import Path
from collections import Counter

from scapy.utils import PcapReader


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASET_DIRS = [
    PROJECT_ROOT / "data" / "raw" / "NonVPN-PCAPs-01",
    PROJECT_ROOT / "data" / "raw" / "VPN-PCAPS-01",
]


def inspect_pcap(pcap_path):
    packet_count = 0
    total_bytes = 0

    try:
        with PcapReader(str(pcap_path)) as reader:
            for packet in reader:
                packet_count += 1
                total_bytes += len(packet)

        return packet_count, total_bytes, None

    except Exception as error:
        return packet_count, total_bytes, str(error)


def main():
    all_files = []

    for folder in DATASET_DIRS:
        if not folder.exists():
            print(f"WARNING: Folder not found: {folder}")
            continue

        all_files.extend(
            path
            for path in folder.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".pcap", ".pcapng"}
        )

    print(f"\nPCAP files found: {len(all_files)}")
    print("=" * 85)

    total_packets = 0
    results = []

    for file_path in sorted(all_files):
        packet_count, total_bytes, error = inspect_pcap(file_path)
        total_packets += packet_count

        results.append((file_path, packet_count, total_bytes, error))

        status = f"ERROR: {error}" if error else "OK"

        print(
            f"{file_path.name:40s} "
            f"packets={packet_count:8d} "
            f"MB={total_bytes / (1024 * 1024):8.2f} "
            f"{status}"
        )

    print("\nSUMMARY")
    print("=" * 40)
    print(f"Capture files: {len(all_files)}")
    print(f"Total packets read: {total_packets}")
    print(
        "Files with errors:",
        sum(1 for _, _, _, error in results if error)
    )

    groups = Counter(
        "VPN" if "VPN-PCAPS-01" in str(path) else "NonVPN"
        for path, _, _, _ in results
    )

    print("\nFiles by capture folder:")
    for name, count in groups.items():
        print(f"{name}: {count}")

        print("\nCAPTURE INVENTORY")
    print("=" * 70)

    for path, packet_count, total_bytes, error in results:
        folder_label = path.parent.name
        print(
            f"folder={folder_label:18s} "
            f"file={path.name:40s} "
            f"packets={packet_count:8d}"
        )


if __name__ == "__main__":
    main()
