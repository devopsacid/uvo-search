window.renderGraph = function (elId, payload) {
  if (!window.vis || !window.vis.Network) return;
  const container = document.getElementById(elId);
  if (!container) return;
  const colorFor = (type) => type === 'procurer' ? '#1d4ed8' : '#059669';
  const nodes = new vis.DataSet(payload.nodes.map(n => ({
    id: n.id, label: n.label,
    color: colorFor(n.type),
    value: Math.max(1, n.value || 1),
    font: { color: '#fff' },
  })));
  const edges = new vis.DataSet(payload.edges.map(e => ({
    from: e.from, to: e.to, label: e.label,
    value: Math.max(1, e.value || 1),
  })));
  const network = new vis.Network(container, { nodes, edges }, {
    nodes: { shape: 'dot', scaling: { min: 8, max: 32 } },
    edges: { scaling: { min: 1, max: 6 }, smooth: false, font: { size: 10 } },
    physics: { stabilization: true },
  });
  network.on('click', (params) => {
    if (params.nodes.length) {
      const id = params.nodes[0];
      window.location.href = '/procurer/' + id;
    }
  });
};
