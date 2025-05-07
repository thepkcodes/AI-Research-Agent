export default async function handler(req, res) {
    if (req.method !== "POST") {
      return res.status(405).json({ message: "Method not allowed" });
    }
  
    const { text, num_results } = req.body;
    if (!text || typeof text !== "string") {
      return res.status(400).json({ message: "Invalid request: text is required" });
    }
  
    // 10s timeout via AbortController
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);
  
    try {
      const backend = await fetch("http://localhost:8000/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, num_results: num_results || 5 }),
        signal: controller.signal,
      });
  
      if (!backend.ok) {
        const errBody = await backend.json().catch(() => ({}));
        throw new Error(errBody.detail || errBody.message || `Status ${backend.status}`);
      }
  
      const data = await backend.json();
      return res.status(200).json(data);
    } catch (err) {
      console.error("Proxy error:", err);
      if (err.name === "AbortError") {
        return res.status(504).json({ message: "Backend request timed out" });
      }
      return res.status(500).json({
        message: err.message || "Internal server error",
        ...(process.env.NODE_ENV === "development" && { stack: err.stack }),
      });
    } finally {
      clearTimeout(timeout);
    }
  }  