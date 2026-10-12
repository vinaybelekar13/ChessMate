/**
 * Tile extraction for the chess-tiles CNN. Port of getChessTilesGray
 * from Elucidation/tensorflow_chessbot (MIT).
 *
 * Crops the board (edge-padding out-of-bounds corners), bilinear
 * resizes to 256x256, normalizes to [0,1], and emits the 64 tiles in
 * the model's input order: tile k = rank*8 + file with A1 at the
 * image's bottom-left, each tile a row-major 32x32 block. Output is
 * a Float32Array of shape [64, 1024].
 */
import type { BoardCorners, GrayImage } from "./detect";
export declare const TILE_INPUT_SIZE: number;
/** Bilinear resize of the corners crop to 256x256, values in [0,1]. */
export declare function extractBoardImage(img: GrayImage, corners: BoardCorners): Float32Array;
/** Slice the 256x256 board into the [64, 1024] model input. */
export declare function boardToTiles(board: Float32Array): Float32Array;
export declare function extractTiles(img: GrayImage, corners: BoardCorners): Float32Array;
/** RGBA ImageData bytes to 0-255 grayscale (ITU-R 601 luma). */
export declare function rgbaToGray(rgba: Uint8ClampedArray, width: number, height: number): GrayImage;
