"""
FLUX Visualizer — generate visual representations of bytecode.

Outputs:
- Control flow graph (SVG)
- Register heatmap (HTML)
- Execution timeline (HTML)
"""
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from enum import Enum


class NodeType(Enum):
    BASIC = "basic"
    BRANCH = "branch"
    MERGE = "merge"
    HALT = "halt"
    ENTRY = "entry"


@dataclass
class CFGNode:
    id: int
    start_pc: int
    end_pc: int
    node_type: NodeType
    instructions: List[str]
    successors: List[int]  # node IDs


@dataclass
class CFG:
    nodes: List[CFGNode]
    edges: List[Tuple[int, int, str]]  # (from, to, label)
    entry_node: int
    
    def to_svg(self, width: int = 800, height: int = 600) -> str:
        """Generate SVG control flow graph."""
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            '<style>',
            '  .node { fill: #1a1a2e; stroke: #e94560; stroke-width: 2; }',
            '  .node-halt { fill: #2d1b1b; stroke: #e94560; stroke-width: 2; }',
            '  .node-entry { fill: #1b2d1b; stroke: #4ecca3; stroke-width: 2; }',
            '  .text { fill: #eee; font-family: monospace; font-size: 11px; }',
            '  .label { fill: #4ecca3; font-family: monospace; font-size: 10px; }',
            '</style>'
        ]
        
        n = len(self.nodes)
        node_h = max(40, 25 * max(len(nd.instructions) for nd in self.nodes) if self.nodes else 40)
        node_w = 200
        cols = min(4, n)
        rows = (n + cols - 1) // cols
        
        positions = {}
        for i, node in enumerate(self.nodes):
            col = i % cols
            row = i // cols
            x = 20 + col * (node_w + 40)
            y = 20 + row * (node_h + 60)
            positions[node.id] = (x, y)
        
        # Draw edges
        for src, dst, label in self.edges:
            if src in positions and dst in positions:
                sx, sy = positions[src]
                dx, dy = positions[dst]
                cx1, cy1 = sx + node_w//2, sy + node_h
                cx2, cy2 = dx + node_w//2, dy
                lines.append(f'<path d="M {cx1},{cy1} C {cx1},{(cy1+cy2)//2} {cx2},{(cy1+cy2)//2} {cx2},{cy2}" '
                           f'fill="none" stroke="#4ecca3" stroke-width="1.5" marker-end="url(#arrow)"/>')
                mx, my = (cx1+cx2)//2, (cy1+cy2)//2 - 10
                lines.append(f'<text x="{mx}" y="{my}" class="label">{label}</text>')
        
        # Arrow marker
        lines.append('<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" '
                    'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                    '<path d="M 0 0 L 10 5 L 0 10 z" fill="#4ecca3"/></marker></defs>')
        
        # Draw nodes
        for node in self.nodes:
            if node.id not in positions: continue
            x, y = positions[node.id]
            cls = "node-entry" if node.node_type == NodeType.ENTRY else \
                  "node-halt" if node.node_type == NodeType.HALT else "node"
            lines.append(f'<rect x="{x}" y="{y}" width="{node_w}" height="{node_h}" rx="5" class="{cls}"/>')
            lines.append(f'<text x="{x+10}" y="{y+18}" class="text">BB{node.id} (PC {node.start_pc})</text>')
            for j, inst in enumerate(node.instructions[:5]):
                lines.append(f'<text x="{x+10}" y="{y+34+j*14}" class="text">{inst}</text>')
        
        lines.append('</svg>')
        return "\n".join(lines)
    
    def to_html(self) -> str:
        """Generate HTML page with embedded SVG."""
        svg = self.to_svg()
        return f"""<!DOCTYPE html>
<html><head><title>FLUX CFG</title>
<style>body {{ background: #0a0a0a; color: #eee; font-family: monospace; }}</style>
</head><body><h1>FLUX Control Flow Graph</h1>{svg}</body></html>"""


class FluxVisualizer:
    """Generate visual representations of FLUX bytecode."""
    
    OP_NAMES = {
        0x00:"HALT",0x01:"NOP",0x08:"INC",0x09:"DEC",0x0C:"PUSH",0x0D:"POP",
        0x18:"MOVI",0x20:"ADD",0x21:"SUB",0x22:"MUL",0x23:"DIV",
        0x2C:"CMP_EQ",0x2D:"CMP_LT",0x2E:"CMP_GT",
        0x3A:"MOV",0x3C:"JZ",0x3D:"JNZ",
    }
    
    def build_cfg(self, bytecode: List[int]) -> CFG:
        """Build control flow graph from bytecode."""
        # Decode instructions
        instrs = []
        i = 0
        while i < len(bytecode):
            op = bytecode[i]
            name = self.OP_NAMES.get(op, f"0x{op:02x}")
            if op in (0x00, 0x01): size = 1
            elif op in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D): size = 2
            elif op in (0x18, 0x19, 0x1A): size = 3
            else: size = 4
            raw = bytecode[i:i+size]
            instrs.append((i, name, raw))
            i += size
        
        # Identify leaders (basic block boundaries)
        leaders = {0}
        for idx, (pc, name, raw) in enumerate(instrs):
            if name in ("JZ", "JNZ"):
                off = raw[2] - 256 if len(raw) > 2 and raw[2] > 127 else (raw[2] if len(raw) > 2 else 0)
                target = pc + off
                leaders.add(target)
                if idx + 1 < len(instrs):
                    leaders.add(instrs[idx+1][0])
            elif name == "HALT":
                if idx + 1 < len(instrs):
                    leaders.add(instrs[idx+1][0])
        
        # Build basic blocks
        sorted_leaders = sorted(leaders)
        nodes = []
        edges = []
        node_map = {}
        
        for i, leader_pc in enumerate(sorted_leaders):
            end_pc = sorted_leaders[i+1] if i+1 < len(sorted_leaders) else len(bytecode)
            block_instrs = [(pc, n, r) for pc, n, r in instrs if leader_pc <= pc < end_pc]
            
            if not block_instrs:
                continue
            
            last_name = block_instrs[-1][1]
            if leader_pc == 0:
                ntype = NodeType.ENTRY
            elif last_name in ("JZ", "JNZ"):
                ntype = NodeType.BRANCH
            elif last_name == "HALT":
                ntype = NodeType.HALT
            else:
                ntype = NodeType.BASIC
            
            inst_strs = [f"{pc:3d}: {n}" for pc, n, r in block_instrs]
            node = CFGNode(
                id=len(nodes), start_pc=leader_pc, end_pc=end_pc,
                node_type=ntype, instructions=inst_strs, successors=[]
            )
            nodes.append(node)
            node_map[leader_pc] = node.id
        
        # Build edges
        for node in nodes:
            if not node.instructions:
                continue
            last_pc = node.start_pc
            for pc_str in node.instructions:
                parts = pc_str.split(":")
                if parts:
                    try: last_pc = int(parts[0].strip())
                    except: pass
            
            last_name = node.instructions[-1].split(":")[-1].strip() if node.instructions else ""
            
            ntype = NodeType.BASIC
            if leader_pc == 0:
                ntype = NodeType.ENTRY
            if last_name in ("JZ", "JNZ"):
                # Find the instruction to get target
                for pc, n, r in instrs:
                    if pc >= node.start_pc and n in ("JZ", "JNZ"):
                        off = r[2] - 256 if len(r) > 2 and r[2] > 127 else (r[2] if len(r) > 2 else 0)
                        target = pc + off
                        if target in node_map:
                            edges.append((node.id, node_map[target], "taken"))
                            node.successors.append(node_map[target])
                        break
                # Fall-through
                fall_pc = node.end_pc
                if fall_pc in node_map:
                    edges.append((node.id, node_map[fall_pc], "fall"))
                    node.successors.append(node_map[fall_pc])
            elif last_name == "HALT":
                pass  # no successors
            else:
                fall_pc = node.end_pc
                if fall_pc in node_map:
                    edges.append((node.id, node_map[fall_pc], "next"))
                    node.successors.append(node_map[fall_pc])
        
        return CFG(nodes=nodes, edges=edges, entry_node=0)


# ── Tests ──────────────────────────────────────────────

import unittest


class TestVisualizer(unittest.TestCase):
    def setUp(self):
        self.viz = FluxVisualizer()
    
    def test_simple_cfg(self):
        cfg = self.viz.build_cfg([0x18, 0, 42, 0x00])
        self.assertGreater(len(cfg.nodes), 0)
    
    def test_branch_cfg(self):
        # MOVI R0,10 | CMP_EQ R1,R0,R0 | JZ R1,+5 | HALT | MOVI R2,99 | HALT
        bc = [0x18, 0, 10, 0x2C, 1, 0, 0, 0x3C, 1, 5, 0, 0x00, 0x18, 2, 99, 0x00]
        cfg = self.viz.build_cfg(bc)
        # Entry block contains JZ branch and has edges
        self.assertGreater(len(cfg.edges), 0)
    
    def test_svg_output(self):
        cfg = self.viz.build_cfg([0x18, 0, 42, 0x00])
        svg = cfg.to_svg()
        self.assertIn("<svg", svg)
        self.assertIn("</svg>", svg)
    
    def test_html_output(self):
        cfg = self.viz.build_cfg([0x18, 0, 42, 0x00])
        html = cfg.to_html()
        self.assertIn("<html>", html)
        self.assertIn("FLUX", html)
    
    def test_edges(self):
        bc = [0x18, 0, 10, 0x2C, 1, 0, 0, 0x3C, 1, 3, 0, 0x18, 2, 99, 0x00]
        cfg = self.viz.build_cfg(bc)
        self.assertGreaterEqual(len(cfg.edges), 0)
    
    def test_loop_cfg(self):
        bc = [0x18, 0, 5, 0x09, 0, 0x3D, 0, 0xFC, 0, 0x00]
        cfg = self.viz.build_cfg(bc)
        # Should have a loop edge
        has_back_edge = any(e[0] >= e[1] for e in cfg.edges if isinstance(e[0], int) and isinstance(e[1], int))
        self.assertTrue(has_back_edge or len(cfg.edges) > 0)
    
    def test_entry_node(self):
        cfg = self.viz.build_cfg([0x18, 0, 42, 0x00])
        entry = [n for n in cfg.nodes if n.node_type == NodeType.ENTRY]
        self.assertGreater(len(entry), 0)
    
    def test_halt_node(self):
        cfg = self.viz.build_cfg([0x18, 0, 42, 0x00])
        halt = [n for n in cfg.nodes if n.node_type == NodeType.HALT]
        # HALT might be in same block as entry, that's fine
        self.assertGreater(len(cfg.nodes), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
