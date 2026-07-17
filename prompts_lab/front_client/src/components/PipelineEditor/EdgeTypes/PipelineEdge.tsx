import React from "react";
import { EdgeProps, getBezierPath, EdgeLabelRenderer } from "@xyflow/react";

export default function PipelineEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  data
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const connectionType = (data?.type as string) || "normal";
  const placeholder = (data?.label as string) || "";

  // Assign edge styling colors based on edge types
  let edgeColor = "var(--normal-edge)";
  let strokeDasharray = undefined;

  if (connectionType === "map") {
    edgeColor = "var(--map-edge)";
    strokeDasharray = "5,5";
  } else if (connectionType === "accum") {
    edgeColor = "var(--accum-edge)";
    strokeDasharray = "2,3";
  }

  const customStyle: React.CSSProperties = {
    ...style,
    stroke: edgeColor,
    strokeWidth: 2,
    strokeDasharray,
    transition: "stroke 0.25s, stroke-width 0.25s",
  };

  return (
    <>
      <path
        id={id}
        className="react-flow__edge-path"
        d={edgePath}
        style={customStyle}
        markerEnd={markerEnd}
      />
      {placeholder && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: "all",
            }}
            className="edge-label-container"
          >
            {connectionType === "map" && (
              <span className="edge-badge map" title="Map connection">↺</span>
            )}
            {connectionType === "accum" && (
              <span className="edge-badge accum" title="Map with Accumulation connection">+ ↺</span>
            )}
            <span>{placeholder}</span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
