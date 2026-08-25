"""Systems diagrams for the Part 3 live layer.

Two pictures, regenerated from this file so they can't drift from the design:

  live_layer_transports.png  -- the three transports side by side
  live_layer_scaleout.png    -- what changes when one process becomes two

Run:  myenv/bin/python docs/diagrams/live_layer.py
Needs graphviz on PATH (`brew install graphviz`).
"""

from pathlib import Path

from diagrams import Cluster, Diagram, Edge, Node
from diagrams.generic.storage import Storage
from diagrams.onprem.client import Client
from diagrams.onprem.compute import Server
from diagrams.onprem.inmemory import Redis
from diagrams.programming.framework import FastAPI, React

OUT = Path(__file__).parent

# Edge colors carry meaning, so the two diagrams read the same way:
#   red    = a cost you are paying repeatedly
#   green  = the error contract survives here
#   orange = the error contract is degraded here
#   black  = plain data flow
COST = "firebrick"
KEEPS = "darkgreen"
LOSES = "darkorange"


# Blank() is the obvious node for a text-only note and does not work: it has an
# icon, so diagrams gives it shape="none" and a transparent 1.9in image, and the
# edge lands on the top of that invisible box with the words drawn near its
# bottom -- an arrow pointing at nothing. A bare Node has _icon = None.
def Note(text: str) -> Node:
    """A visible text box, sized to its own text. Every attribute here overrides
    one of Diagram._default_node_attrs, which pins nodes to a fixed 1.4in square
    and anchors labels to the bottom edge -- right for an icon with a caption,
    wrong for a box that is only caption."""
    return Node(
        label=text,
        shape="box",
        style="rounded,filled",
        fillcolor="white",
        color="gray55",
        fontsize="11",
        margin="0.22,0.16",
        fixedsize="false",
        # Minimums once fixedsize is off, so the label decides.
        width="0.1",
        height="0.1",
        labelloc="c",
    )


GRAPH_ATTR = {
    "fontsize": "20",
    "bgcolor": "white",
    "pad": "0.4",
    "splines": "spline",
    # Cluster-to-cluster edges below confuse the default ranker ("trouble in
    # init_rank"); newrank makes ranking global instead of per-cluster.
    "newrank": "true",
    "nodesep": "0.6",
    "ranksep": "1.1",
}


def transports() -> None:
    """The three paths side by side. Read each column top to bottom.

    Long-form commentary lives in Note() boxes rather than edge labels --
    graphviz routes labelled edges around each other and the text ends up
    orbiting the picture instead of sitting next to what it describes.
    """
    with Diagram(
        "Part 3 live layer -- three transports, one API instance",
        filename=str(OUT / "live_layer_transports"),
        show=False,
        direction="TB",
        outformat="png",
        graph_attr=GRAPH_ATTR,
    ):
        # --- 1. what you have today -----------------------------------------
        with Cluster("1. REST polling  (baseline -- useSchedule today)"):
            poll_ui = React("useSchedule.load()\nwrapped in setInterval")
            poll_api = FastAPI("GET /api/schedule\nfull request/response")
            poll_db = Storage("DuckDB\nredsox_25.duckdb")
            poll_note = Note(
                "CONTRACT: fully intact\n"
                "every tick is a whole HTTP transaction,\n"
                "so 200 / 404 / 503 + envelope all still work.\n"
                "errors.ts needs ZERO changes."
            )

            (
                poll_ui
                >> Edge(label="  1 request PER CLIENT\n  per tick", color=COST)
                >> poll_api
            )
            (
                poll_api
                >> Edge(
                    label="  get_conn() opens a NEW\n  connection every request",
                    color=COST,
                )
                >> poll_db
            )
            poll_api >> Edge(color=KEEPS, style="dotted") >> poll_note
            # invisible edge: ranks the note BELOW the bottom row so the
            # two labels stop overlapping. No meaning, layout only.
            poll_db >> Edge(style="invis") >> poll_note

        # --- 2. the honest choice for a read-only feed ------------------------
        with Cluster("2. SSE  (server -> client only, still HTTP)"):
            sse_ui = React("new EventSource()\nbrowser auto-reconnects")
            sse_api = FastAPI("GET /api/live/{gamePk}\nStreamingResponse, held open")
            sse_tick = Server("replay ticker\n1 read per TICK, not per client")
            sse_db = Storage("DuckDB\nline_score_innings")
            sse_note = Note(
                "CONTRACT: half intact on the wire,\n"
                "LESS than half in the browser\n"
                "BEFORE the 1st byte -> real 404 + envelope,\n"
                "  but EventSource discards a non-200 BODY:\n"
                "  the hook only sees error + readyState CLOSED\n"
                "AFTER  the 1st byte -> must be a `failure` event"
            )

            sse_ui >> Edge(label="  ONE request, never closed", color=KEEPS) >> sse_api
            (
                sse_tick
                >> Edge(
                    label="  ONE query per tick,\n  regardless of client count",
                    color=KEEPS,
                )
                >> sse_db
            )
            sse_tick >> Edge(label="  yields each inning") >> sse_api
            (
                sse_api
                >> Edge(label="  data: {...}\n  ONE direction only", style="dashed")
                >> sse_ui
            )
            sse_api >> Edge(color=LOSES, style="dotted") >> sse_note
            sse_db >> Edge(style="invis") >> sse_note

        # --- 3. the one built to feel the cost --------------------------------
        with Cluster("3. Websocket  (two-way, HTTP gone after the handshake)"):
            ws_ui = React(
                "new WebSocket()\nYOU write: absolute ws:// URL,\nreconnect, backoff, giving up"
            )
            ws_api = FastAPI("WS /api/live/ws/{gamePk}\nGET + Upgrade -> 101")
            ws_list = Server(
                "the SAME Broadcaster registry\ndict[int, set[Queue]]\nno second connection list"
            )
            ws_tick = Server("replay ticker\n1 read per TICK")
            ws_db = Storage("DuckDB\nline_score_innings")
            ws_note = Note(
                "CONTRACT: rebuilt by hand, and BETTER\n"
                "  than SSE at reaching the browser\n"
                "no middleware, no handler: both are HTTP-only,\n"
                "  so the request_id is minted in the route\n"
                "ACCEPT FIRST, then send the envelope as a frame --\n"
                "  a rejected handshake reaches JS as a bare 1006\n"
                "COST: every failure now looks like a 101 on the wire"
            )

            (
                ws_ui
                >> Edge(
                    label="  handshake: the ONLY\n  HTTP moment you get", color=KEEPS
                )
                >> ws_api
            )
            (
                ws_api
                >> Edge(label="  subscribe() on accept\n  unsubscribe() on disconnect")
                >> ws_list
            )
            ws_tick >> Edge(label="  ONE query per tick", color=KEEPS) >> ws_db
            (
                ws_tick
                >> Edge(
                    label="  THE FAN-OUT IS A FOR-LOOP\n  (shared with SSE -- live.py\n  imports no transport)",
                    color=KEEPS,
                )
                >> ws_list
            )
            ws_list >> Edge(label="  frames, BOTH directions", style="dashed") >> ws_ui
            ws_api >> Edge(color=LOSES, style="dotted") >> ws_note
            ws_db >> Edge(style="invis") >> ws_note
            ws_list >> Edge(style="invis") >> ws_note


def scaleout() -> None:
    """Same ticker, same for-loop, one extra process -- and it breaks."""
    with Diagram(
        "What actually forces a bus: a second process",
        filename=str(OUT / "live_layer_scaleout"),
        show=False,
        direction="TB",
        outformat="png",
        graph_attr=GRAPH_ATTR,
    ):
        with Cluster("TODAY -- one uvicorn process, no bus needed"):
            a_users = Client("every client\nlands in the same process")
            a_tick = Server("ticker\n(inside process 1)")
            a_list = Server("process 1\nconnections: []\nALL sockets, ONE memory space")

            a_users >> Edge(label="  ws connect") >> a_list
            (
                a_tick
                >> Edge(
                    label="  for-loop reaches EVERY client\n  correct, not a shortcut",
                    color=KEEPS,
                    style="bold",
                )
                >> a_list
            )

        with Cluster("LATER -- two processes, the SAME for-loop goes blind"):
            b_users = Client("clients are\nload-balanced across copies")
            b_tick = Server("ticker\n(inside process 1)\nSAME CODE AS ABOVE")
            b_list1 = Server("process 1\nconnections: []\nclient A only")
            b_list2 = Server("process 2\nconnections: []\nclient B only")
            b_bus = Redis(
                "Redis pub/sub = THE BUS\nreplaces the LIST,\nnot the for-loop"
            )
            b_ingest = Server(
                "ingest script\nsox_2025/scripts/\nALREADY a separate process"
            )

            b_users >> Edge(label="  A") >> b_list1
            b_users >> Edge(label="  B") >> b_list2
            b_tick >> Edge(label="  reaches A\n  same memory", color=KEEPS) >> b_list1
            (
                b_tick
                >> Edge(
                    label="  CANNOT reach B\n  different memory space",
                    color=COST,
                    style="bold",
                )
                >> b_list2
            )
            b_tick >> Edge(label="  publish", color=KEEPS) >> b_bus
            (
                b_ingest
                >> Edge(
                    label="  publish -- the realistic\n  reason YOU would need one",
                    color=KEEPS,
                )
                >> b_bus
            )
            b_bus >> Edge(label="  subscribe", color=KEEPS) >> b_list1
            b_bus >> Edge(label="  subscribe", color=KEEPS) >> b_list2


if __name__ == "__main__":
    transports()
    scaleout()
    print("wrote:")
    for p in sorted(OUT.glob("*.png")):
        print(" ", p)
