"""Export pipeline results to JSON, XML, and EDL formats."""
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List


def to_json(video_id: str, duration: float, content_type: str,
            mode: str, results: list) -> str:
    payload = {
        "video_id": video_id,
        "duration": duration,
        "content_type": content_type,
        "mode": mode,
        "results": results,
    }
    return json.dumps(payload, indent=2)


def to_xml(video_id: str, duration: float, content_type: str,
           mode: str, results: list) -> str:
    root = ET.Element("segmentation")
    root.set("video_id", video_id)
    root.set("duration", str(duration))
    root.set("content_type", content_type)
    root.set("mode", mode)

    results_el = ET.SubElement(root, "results")
    for r in results:
        result_el = ET.SubElement(results_el, "result")
        for key, val in r.items():
            child = ET.SubElement(result_el, key)
            child.text = str(val)

    rough = ET.tostring(root, encoding="unicode")
    reparsed = minidom.parseString(rough)
    return reparsed.toprettyxml(indent="  ")


def to_edl(video_id: str, results: list, fps: float = 25.0) -> str:
    """Export as CMX 3600 EDL format."""
    lines = [
        f"TITLE: SegmentIQ — {video_id}",
        "FCM: NON-DROP FRAME",
        "",
    ]

    event_num = 1
    for r in results:
        if r["start"] == r["end"]:  # Break point
            continue

        def tc(secs: float) -> str:
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            s = int(secs % 60)
            f = int((secs - int(secs)) * fps)
            return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

        lines.append(f"{event_num:03d}  001  V  C  {tc(r['start'])} {tc(r['end'])} {tc(r['start'])} {tc(r['end'])}")
        lines.append(f"* TYPE: {r['type'].upper()}")
        lines.append(f"* CONFIDENCE: {r['confidence']:.2f}")
        lines.append(f"* DESC: {r['description']}")
        lines.append("")
        event_num += 1

    return "\n".join(lines)
