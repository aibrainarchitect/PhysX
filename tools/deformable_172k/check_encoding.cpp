// Verify the actual shared CPU/GPU encoding helpers, including reserved indices.
#include "PxgSimulationCoreDesc.h"
#include <cstdio>
#include <cstdlib>

using namespace physx;

static void require(bool condition)
{
    if (!condition)
    {
        std::fputs("deformable encoding check failed\n", stderr);
        std::exit(1);
    }
}

int main()
{
    static_assert(PX_MAX_NB_DEFORMABLE_VOLUME >= 172032, "target actor count must fit");
    static_assert(PX_MAX_NB_DEFORMABLE_VOLUME_TET > 14237, "target mesh must fit");
    static_assert(PX_MAX_NB_DEFORMABLE_SURFACE == 4095, "surface layout must stay unchanged");
    static_assert(PX_MAX_NB_DEFORMABLE_SURFACE_TRI == 1048575, "surface layout must stay unchanged");
    const PxU32 elements[] = {0, 1, 14237, PX_MAX_NB_DEFORMABLE_VOLUME_TET - 1,
                              PX_MAX_NB_DEFORMABLE_VOLUME_TET};
    PxU32 previous = 0;
    for (PxU32 actor = 0; actor < PX_MAX_NB_DEFORMABLE_VOLUME; ++actor)
    {
        for (PxU32 element : elements)
        {
            const PxU32 packed = PxEncodeSoftBodyIndex(actor, element);
            require(PxGetSoftBodyId(packed) == actor);
            require(PxGetSoftBodyElementIndex(packed) == element);
            require(packed != 0xffffffffu);
            require((actor == 0 && element == 0) || packed > previous);
            previous = packed;
        }
    }
    const PxU32 surfaceElements[] = {0, 1, 16383, 16384, 1048574, 1048575};
    for (PxU32 actor = 0; actor < PX_MAX_NB_DEFORMABLE_SURFACE; ++actor)
    {
        for (PxU32 element : surfaceElements)
        {
            const PxU32 packed = PxEncodeClothIndex(actor, element);
            require(PxGetClothId(packed) == actor);
            require(PxGetClothElementIndex(packed) == element);
            require(packed != 0xffffffffu);
        }
    }
    std::puts("PASS: 262143 volume IDs, tetrahedron boundaries/wildcard, unchanged surface encoding");
}
