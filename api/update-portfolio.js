export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { action, symbol, data } = req.body;
  const GITHUB_USER = "avichy";
  const GITHUB_REPO = "stock-portfolio-bot";
  const FILE_PATH = "portfolio.json";
  const TOKEN = process.env.GH_TOKEN; // נשמר בצורה מאובטחת בשרת

  if (!TOKEN) {
    return res.status(500).json({ error: 'Server token not configured' });
  }

  try {
    // 1. שליפת הקובץ הנוכחי מ-GitHub
    const getRes = await fetch(`https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/contents/${FILE_PATH}`, {
      headers: { "Authorization": `token ${TOKEN}` }
    });
    if (!getRes.ok) throw new Error("Failed to fetch file from GitHub");
    
    const fileData = await getRes.json();
    const content = JSON.parse(decodeURIComponent(escape(atob(fileData.content))));

    // 2. עדכון הנתונים (הוספה/עריכה או מחיקה)
    if (action === 'upsert') {
      content[symbol] = data;
    } else if (action === 'delete') {
      delete content[symbol];
    }

    // 3. שמירת הקובץ חזרה ל-GitHub
    const putRes = await fetch(`https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/contents/${FILE_PATH}`, {
      method: "PUT",
      headers: {
        "Authorization": `token ${TOKEN}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: `API update: ${action} ${symbol}`,
        content: btoa(unescape(encodeURIComponent(JSON.stringify(content, null, 2)))),
        sha: fileData.sha
      })
    });

    if (!putRes.ok) throw new Error("Failed to update file on GitHub");

    return res.status(200).json({ success: true });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
