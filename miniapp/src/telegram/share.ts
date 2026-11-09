// ST-07: Telegram's story editor and file download for share cards. Imported only by the
// lazy share sheet, so the initial bundle doesn't carry it.
import { downloadFile, retrieveLaunchParams, shareStory } from "@telegram-apps/sdk-react";

export const BOT_LINK = "https://t.me/tristhana_bot";

/** Mobile clients (Mini Apps 7.8+); never desktop or web. */
export function canShareStory(): boolean {
  return shareStory.isAvailable();
}

/** Bot API 8.0+ clients. */
export function canDownload(): boolean {
  return downloadFile.isAvailable();
}

/** Telegram allows a link in a story for Premium users only (Q206). */
export function isPremium(): boolean {
  try {
    return retrieveLaunchParams().tgWebAppData?.user?.is_premium === true;
  } catch {
    return false;
  }
}

export function shareToStory(imageUrl: string, caption: string): void {
  if (!shareStory.isAvailable()) return;
  shareStory(imageUrl, {
    text: caption,
    ...(isPremium() ? { widgetLink: { url: BOT_LINK, name: "Tristhana" } } : {}),
  });
}

/** Telegram's native "save file" dialog. Resolves false when unavailable or refused. */
export async function saveImage(url: string, fileName: string): Promise<boolean> {
  if (!downloadFile.isAvailable()) return false;
  try {
    await downloadFile(url, fileName);
    return true;
  } catch {
    return false;
  }
}
