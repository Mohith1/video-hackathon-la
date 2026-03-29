"use client";
import { forwardRef, useRef, useState } from "react";
import dynamic from "next/dynamic";

const ReactPlayer = dynamic(() => import("react-player/lazy"), { ssr: false });

interface Props {
  url: string;
  playerRef: React.RefObject<any>;
  onProgress?: (state: { playedSeconds: number }) => void;
}

export default function VideoPlayer({ url, playerRef, onProgress }: Props) {
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(0.8);

  return (
    <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
      <ReactPlayer
        ref={playerRef}
        url={url}
        playing={playing}
        volume={volume}
        width="100%"
        height="100%"
        onProgress={onProgress}
        controls
        config={{
          file: {
            attributes: {
              crossOrigin: "anonymous",
            },
          },
        }}
      />
    </div>
  );
}
