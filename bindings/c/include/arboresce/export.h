#ifndef ARBORESCE_EXPORT_H
#define ARBORESCE_EXPORT_H

#if defined(_WIN32)
#if defined(ARBORESCE_STATIC)
#define ARBORESCE_API __cdecl
#elif defined(ARBORESCE_BUILDING_SHARED)
#define ARBORESCE_API __declspec(dllexport) __cdecl
#else
#define ARBORESCE_API __declspec(dllimport) __cdecl
#endif
#else
#define ARBORESCE_API __attribute__((visibility("default")))
#endif

#endif
