"use server";

import { revalidatePath } from "next/cache";

import { backendFetch } from "@/lib/backend";

export async function toggleLikeAction(formData: FormData) {
  const animeId = Number(formData.get("animeId") || 0);
  const liked = String(formData.get("liked") || "true") === "true";
  await backendFetch(`/ui/api/anime/${animeId}/like`, {
    method: "POST",
    body: JSON.stringify({ user_id: 1, liked }),
  });
  revalidatePath(`/anime/${animeId}`);
}

export async function setTagAction(formData: FormData) {
  const animeId = Number(formData.get("animeId") || 0);
  const tag = String(formData.get("tag") || "").trim();
  await backendFetch(`/ui/api/anime/${animeId}/tag`, {
    method: "POST",
    body: JSON.stringify({ user_id: 1, tag }),
  });
  revalidatePath(`/anime/${animeId}`);
}

export async function startDownloadAction(formData: FormData) {
  const animeId = Number(formData.get("animeId") || 0);
  const url = String(formData.get("url") || "").trim();
  await backendFetch(`/ui/api/anime/${animeId}/download`, {
    method: "POST",
    body: JSON.stringify({ user_id: 1, url }),
  });
  revalidatePath("/downloads");
  revalidatePath(`/anime/${animeId}`);
}

export async function cancelDownloadAction(formData: FormData) {
  const animeId = Number(formData.get("animeId") || 0);
  await backendFetch(`/ui/api/anime/${animeId}/cancel`, {
    method: "POST",
  });
  revalidatePath("/downloads");
  revalidatePath(`/anime/${animeId}`);
}
