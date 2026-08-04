export default async function handler(req, res) {
  const GITHUB_USER = "avichy";
  const GITHUB_REPO = "stock-portfolio-bot";
  const FILE_PATH = "portfolio.json";
  const TOKEN = process.env.GH_TOKEN; // נשמר בצורה מאובטחת בשרת

  if (!TOKEN) {
    return res.status(500).json({ error: 'Server token not configured' });
  }

  const headers = {
    "Authorization": `token ${TOKEN}`,
    "Accept": "application/vnd.github.v3+json"
  };

  try {
    // 1. טיפול בבקשת GET - טעינת המניות והצגתן באתר (פותר את התקיעה)
    if (req.method === 'GET') {
      const getRes = await fetch(`https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/contents/${FILE_PATH}`, { headers });
      
      if (!getRes.ok) {
        if (getRes.status === 404) return res.status(200).json({});
        throw new Error("Failed to fetch file from GitHub");
      }
      
      const fileData = await getRes.json();
      const content = JSON.parse(Buffer.from(fileData.content, 'base64').toString('utf8'));
      return res.status(200).json(content);
    }

    // 2. טיפול בבקשת POST - הוספה, עדכון או מחיקת מניה
    if (req.method === 'POST') {
      // שליפת הנתונים הנוכחיים כדי לקבל SHA מעודכן
      const getRes = await fetch(`https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/contents/${FILE_PATH}`, { headers });
      if (!getRes.ok) throw new Error("Failed to fetch file from GitHub");
      
      const fileData = await getRes.json();
      const content = JSON.parse(Buffer.from(fileData.content, 'base64').toString('utf8'));

      const { action, symbol, data } = req.body || {};

      if (action === 'upsert' && symbol) {
        content[symbol] = data;
      } else if (action === 'delete' && symbol) {
        delete content[symbol];
      }

      // שמירת הקובץ חזרה ל-GitHub
      const updatedJsonStr = JSON.stringify(content, null, 2);
      const encodedContent = Buffer.from(updatedJsonStr, 'utf8').toString('base64');

      const putRes = await fetch(`https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/contents/${FILE_PATH}`, {
        method: "PUT",
        headers: {
          ...headers,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          message: `API update: ${action || 'save'} ${symbol || ''}`,
          content: encodedContent,
          sha: fileData.sha
        })
      });

      if (!putRes.ok) throw new Error("Failed to update file on GitHub");

      return res.status(200).json({ success: true });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
